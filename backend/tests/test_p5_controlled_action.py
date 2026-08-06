"""P5 受控联合索引动作的结构化提案测试。"""

from uuid import uuid4

from src.application.contracts import DiagnosisExecutionResult
from src.domain.diagnosis import DiagnosisSeverity
from src.domain.evidence import EvidenceInvestigationResult, MissingIndexSignal, RootCauseFact
from src.domain.records import DiagnosisRunData
from src.domain.actions import ActionProposalData
from src.application.action_execution import ActionPreconditionBlockedError
from src.infrastructure.actions.postgres_target_executor import PostgresTargetActionExecutor
from src.application.action_services import _root_cause_id
from src.domain.records import DiagnosisResultData
from src.infrastructure.diagnosis.result_assembler import KernelReportResultAssembler


def _signal() -> MissingIndexSignal:
    return MissingIndexSignal(
        service_id="postgres-target",
        schema="public",
        table="orders",
        columns=("customer_id", "created_at"),
        index_name="idx_orders_customer_created_at",
    )


def _investigation() -> EvidenceInvestigationResult:
    return EvidenceInvestigationResult(
        summary="确认固定目标存在缺索引信号。",
        severity=DiagnosisSeverity.HIGH,
        confidence=0.95,
        root_causes=[RootCauseFact(
            title="缺少固定联合索引",
            summary="只读诊断确认固定目标存在 seq scan 信号。",
            confidence=0.95,
            missing_index=_signal(),
        )],
        missing_index=_signal(),
    )


def test_结果组装器保留结构化缺索引信号() -> None:
    run = DiagnosisRunData(session_id=uuid4(), input_message_id=uuid4())
    result = KernelReportResultAssembler().assemble(
        run,
        DiagnosisExecutionResult(
            report="报告正文不能作为动作触发依据。",
            evidence_investigation=_investigation(),
        ),
    )

    assert result.root_causes[0]["missing_index"]["table"] == "orders"
    assert len(result.evidence) >= 3


def test_缺索引信号保留固定列顺序() -> None:
    assert _signal().columns == ("customer_id", "created_at")


def test_提案根因必须绑定匹配的缺索引信号() -> None:
    signal = _signal().model_dump(mode="json", by_alias=True)
    evidence_ids = [uuid4(), uuid4(), uuid4()]
    expected_root_cause_id = uuid4()
    unrelated_root_cause_id = uuid4()
    result = DiagnosisResultData(
        run_id=uuid4(),
        summary="固定缺索引事实",
        severity=DiagnosisSeverity.HIGH,
        confidence=1.0,
        root_causes=[
            {
                "id": str(unrelated_root_cause_id),
                "title": "另一个信号",
                "summary": "不应被绑定",
                "confidence": 1.0,
                "evidence_ids": [str(evidence_ids[0])],
                "missing_index": {**signal, "table": "other_table"},
            },
            {
                "id": str(expected_root_cause_id),
                "title": "固定信号",
                "summary": "应被绑定",
                "confidence": 1.0,
                "evidence_ids": [str(item) for item in evidence_ids],
                "missing_index": signal,
            },
        ],
        evidence=[{"id": str(item), "source_type": "database"} for item in evidence_ids],
        recommendations=[],
        risks=[],
        requires_approval=True,
        agent_summary=[],
    )

    assert _root_cause_id(result, evidence_ids, signal) == expected_root_cause_id


def _proposal() -> ActionProposalData:
    run_id = uuid4()
    root_id = uuid4()
    evidence_ids = [uuid4(), uuid4(), uuid4()]
    from src.application.action_services import (
        COMPOUND_INDEX_ACTION_ID,
        COMPOUND_INDEX_VERIFICATION_PLAN,
        TARGET_COLUMNS,
        TARGET_INDEX_NAME,
        TARGET_SCHEMA,
        TARGET_SERVICE_ID,
        TARGET_TABLE,
    )
    from src.domain.actions import action_digest
    target = {
        "service_id": TARGET_SERVICE_ID,
        "schema": TARGET_SCHEMA,
        "table": TARGET_TABLE,
        "columns": ",".join(TARGET_COLUMNS),
        "index_name": TARGET_INDEX_NAME,
    }
    return ActionProposalData(
        source_run_id=run_id,
        action_id=COMPOUND_INDEX_ACTION_ID,
        action_digest=action_digest(
            action_id=COMPOUND_INDEX_ACTION_ID,
            source_run_id=run_id,
            root_cause_id=root_id,
            evidence_ids=evidence_ids,
            target=target,
            verification_plan=COMPOUND_INDEX_VERIFICATION_PLAN,
        ),
        mode="target",
        title="重建受控靶场联合索引",
        description="只对受控靶场固定目标执行代码内联合索引动作。",
        target=target,
        root_cause_id=root_id,
        evidence_ids=evidence_ids,
        risk_summary="这是受控靶场结构变更；生产和预发布实例不会执行。",
        verification_plan=COMPOUND_INDEX_VERIFICATION_PLAN,
    )


class _FakeConnection:
    def __init__(self, *, index_exists: bool = False, verify_ok: bool = True) -> None:
        self.index_exists = index_exists
        self.verify_ok = verify_ok
        self.statements: list[str] = []
        self.autocommit = False

    def execution_options(self, **options: object) -> "_FakeConnection":
        self.autocommit = options.get("isolation_level") == "AUTOCOMMIT"
        return self

    def execute(self, statement: object, *_args: object, **_kwargs: object) -> object:
        sql = str(statement)
        self.statements.append(sql)
        if "to_regclass" in sql:
            return _ScalarResult("public.orders")
        if "pg_index" in sql or "index_ns" in sql:
            return _ScalarResult(self.index_exists)
        if "EXPLAIN" in sql:
            if not self.verify_ok:
                return _MappingResult([])
            return _MappingResult([{"QUERY PLAN": [{"Plan": {"Node Type": "Index Scan", "Index Name": "idx_orders_customer_created_at"}}]}])
        return _ScalarResult(True)

    def close(self) -> None:
        pass


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self.value = value

    def scalar(self) -> object:
        return self.value


class _MappingResult:
    def __init__(self, values: list[dict[str, object]]) -> None:
        self.values = values

    def mappings(self) -> "_MappingResult":
        return self

    def all(self) -> list[dict[str, object]]:
        return self.values


class _FakeEngine:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection
        self.disposed = False

    def connect(self) -> _FakeConnection:
        return self.connection

    def dispose(self) -> None:
        self.disposed = True


def test_生产目标在建立连接前被拦截() -> None:
    executor = PostgresTargetActionExecutor(None, engine_factory=lambda _dsn: None)
    proposal = _proposal().model_copy(update={"target": {"service_id": "postgres-production"}})

    try:
        executor.execute(proposal)
    except ActionPreconditionBlockedError:
        pass
    else:
        raise AssertionError("生产目标必须被拦截")


def test_固定动作使用_autocommit_并先通过前置条件() -> None:
    connection = _FakeConnection()
    engine = _FakeEngine(connection)
    executor = PostgresTargetActionExecutor("target-dsn", engine_factory=lambda _dsn: engine)

    result = executor.execute(_proposal())

    assert connection.autocommit is True
    assert any("CREATE INDEX CONCURRENTLY" in statement for statement in connection.statements)
    assert result.mode == "target"
