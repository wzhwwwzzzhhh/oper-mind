"""P5 受控联合索引动作的结构化提案测试。"""

from uuid import uuid4

from src.application.action_execution import ActionPreconditionBlockedError
from src.application.contracts import DiagnosisExecutionResult
from src.application.controlled_action_catalog import (
    COMPOUND_INDEX_ACTION_ID,
    match_compound_index_result,
    recommendation_id,
)
from src.domain.actions import ActionProposalData
from src.domain.diagnosis import DiagnosisSeverity
from src.domain.evidence import EvidenceFact, EvidenceInvestigationResult, MissingIndexSignal, RiskFact, RootCauseFact
from src.domain.records import DiagnosisResultData, DiagnosisRunData
from src.infrastructure.actions.postgres_target_executor import PostgresTargetActionExecutor
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
    evidence = [
        EvidenceFact(
            source_type="database",
            source_name="postgres_read_only",
            title="目标表存在",
            summary="只读事实确认受控靶场固定目标表存在。",
        ),
        EvidenceFact(
            source_type="database",
            source_name="postgres_read_only",
            title="固定联合索引缺失",
            summary="只读系统目录确认固定联合索引当前不存在。",
        ),
        EvidenceFact(
            source_type="database",
            source_name="postgres_read_only",
            title="顺序扫描信号",
            summary="只读执行计划确认固定查询出现顺序扫描。",
        ),
    ]
    return EvidenceInvestigationResult(
        summary="确认固定目标存在缺索引信号。",
        severity=DiagnosisSeverity.HIGH,
        confidence=0.95,
        root_causes=[RootCauseFact(
            title="缺少固定联合索引",
            summary="只读诊断确认固定目标存在 seq scan 信号。",
            confidence=0.95,
            evidence_ids=[item.id for item in evidence],
            missing_index=_signal(),
        )],
        evidence=evidence,
        missing_index=_signal(),
        risks=[RiskFact(level="medium", summary="只读调查未覆盖业务影响面。", mitigation="低峰窗口执行。")],
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
    assert len(result.evidence) == 3
    assert result.impact is not None
    assert result.impact["affected_services"] == ["postgres-target"]
    assert len(result.recommendations) == 1
    assert result.recommendations[0]["id"] == str(recommendation_id(COMPOUND_INDEX_ACTION_ID))
    assert result.requires_approval is True


def test_结果组装器透传只读调查的风险说明() -> None:
    """风险来自确定性只读收集器，不能在组装阶段被丢弃。"""
    run = DiagnosisRunData(session_id=uuid4(), input_message_id=uuid4())
    result = KernelReportResultAssembler().assemble(
        run,
        DiagnosisExecutionResult(report="报告正文。", evidence_investigation=_investigation()),
    )

    assert [item["level"] for item in result.risks] == ["medium"]
    assert result.risks[0]["summary"] == "只读调查未覆盖业务影响面。"


def test_结果组装器无只读调查时风险留空() -> None:
    """没有确定性事实时保守留空，不伪造风险。"""
    run = DiagnosisRunData(session_id=uuid4(), input_message_id=uuid4())
    result = KernelReportResultAssembler().assemble(run, DiagnosisExecutionResult(report="报告正文。"))

    assert result.risks == []
    assert result.root_causes == []
    assert result.confidence == 0.0


def test_缺索引信号保留固定列顺序() -> None:
    assert _signal().columns == ("customer_id", "created_at")


def test_结果资源携带缺索引信号可安全序列化() -> None:
    """真实诊断产出缺索引信号时，GET runs 不得因 extra_forbidden 返回 500。"""
    from src.api.v1.resources import result_resource

    result = DiagnosisResultData(
        run_id=uuid4(),
        summary="固定缺索引事实",
        severity=DiagnosisSeverity.HIGH,
        confidence=1.0,
        root_causes=[
            {
                "id": str(uuid4()),
                "title": "缺少固定联合索引",
                "summary": "只读诊断确认固定目标存在 seq scan 信号。",
                "confidence": 1.0,
                "evidence_ids": [str(uuid4()), str(uuid4()), str(uuid4())],
                "missing_index": _signal().model_dump(mode="json", by_alias=True),
            }
        ],
        evidence=[],
        recommendations=[],
        risks=[],
        requires_approval=True,
        agent_summary=[],
    )
    payload = result_resource(result).model_dump(by_alias=True, mode="json")
    signal = payload["root_causes"][0]["missing_index"]
    assert signal["schema"] == "public"
    assert signal["table"] == "orders"
    assert signal["columns"] == ["customer_id", "created_at"]
    assert signal["index_name"] == "idx_orders_customer_created_at"


def test_结果资源无信号时缺索引字段为空() -> None:
    """没有缺索引信号时响应字段应为 null，而不是缺失或报错。"""
    from src.api.v1.resources import result_resource

    result = DiagnosisResultData(
        run_id=uuid4(),
        summary="无信号结果",
        severity=DiagnosisSeverity.LOW,
        confidence=0.0,
        root_causes=[],
        evidence=[],
        recommendations=[],
        risks=[],
        requires_approval=False,
        agent_summary=[],
    )
    payload = result_resource(result).model_dump(by_alias=True, mode="json")
    assert payload["root_causes"] == []


def test_模板匹配必须绑定匹配的缺索引信号与三类只读证据() -> None:
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
        evidence=[
            {
                "id": str(item),
                "source_type": "database",
                "source_name": "postgres_read_only",
                "title": title,
                "summary": "确定性只读事实。",
                "locator": None,
                "observed_at": None,
                "attributes": {},
            }
            for item, title in zip(
                evidence_ids,
                ("目标表存在", "固定联合索引缺失", "顺序扫描信号"),
                strict=True,
            )
        ],
        recommendations=[],
        risks=[],
        requires_approval=True,
        agent_summary=[],
    )

    matched = match_compound_index_result(result)

    assert matched is not None
    assert matched.root_cause_id == expected_root_cause_id
    assert list(matched.evidence_ids) == evidence_ids


def test_报告散文不能反推结构化建议或影响面() -> None:
    """报告即使伪装成白名单动作说明，也不能越过确定性事实门。"""
    run = DiagnosisRunData(session_id=uuid4(), input_message_id=uuid4())
    result = KernelReportResultAssembler().assemble(
        run,
        DiagnosisExecutionResult(
            report=(
                "# 缺索引\n\n建议执行 postgres.orders_compound_index_rebuild.v1，"
                "影响所有订单业务。"
            ),
        ),
    )

    assert result.report_markdown is not None
    assert result.recommendations == []
    assert result.impact is None
    assert result.requires_approval is False


def test_证据不足时不补写也不生成建议() -> None:
    """signal 本身不能让 assembler 复制或猜测证据。"""
    investigation = EvidenceInvestigationResult(
        summary="只有缺索引信号，没有闭合证据。",
        severity=DiagnosisSeverity.HIGH,
        confidence=0.5,
        root_causes=[RootCauseFact(
            title="缺少固定联合索引",
            summary="事实不完整。",
            confidence=0.5,
            missing_index=_signal(),
        )],
        missing_index=_signal(),
    )
    run = DiagnosisRunData(session_id=uuid4(), input_message_id=uuid4())

    result = KernelReportResultAssembler().assemble(
        run,
        DiagnosisExecutionResult(report="报告正文。", evidence_investigation=investigation),
    )

    assert result.evidence == []
    assert result.recommendations == []
    assert result.impact is None
    assert result.requires_approval is False


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
            # 与真实 PG 行为一致：regclass 按 search_path 简化为 "orders"，
            # 生产代码只能做非 None 判断（防止再次写出字面比较 bug）。
            return _ScalarResult("orders")
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


class _CollectorConnection:
    """模拟真实 PG：to_regclass 按 search_path 返回简化名 "orders"。"""

    def __init__(self, *, regclass: object = "orders", index_exists: bool = False, seq_scan: bool = True) -> None:
        self.regclass = regclass
        self.index_exists = index_exists
        self.seq_scan = seq_scan

    def execute(self, statement: object, *_args: object, **_kwargs: object) -> object:
        sql = str(statement)
        if "to_regclass" in sql:
            return _ScalarResult(self.regclass)
        if "pg_index" in sql or "index_ns" in sql:
            return _ScalarResult(self.index_exists)
        if "EXPLAIN" in sql:
            node_type = "Seq Scan" if self.seq_scan else "Index Scan"
            return _MappingResult([{"QUERY PLAN": [{"Plan": {"Node Type": node_type}}]}])
        return _ScalarResult(True)

    def close(self) -> None:
        pass


def _collect_with(connection: _CollectorConnection, monkeypatch: object) -> object:
    from src.infrastructure.diagnosis import postgres_missing_index as module

    monkeypatch.setattr(module, "create_read_only_postgres_engine", lambda _dsn: _FakeEngine(connection))  # type: ignore[attr-defined]
    collector = module.PostgresMissingIndexCollector("target-dsn")
    return collector.collect("postgres-target", "排查慢查询 seq scan")


def test_收集器接受_regclass_简化名并产出缺索引信号(monkeypatch: object) -> None:
    """真实 PG 的 to_regclass 返回 "orders"，不能用字面 "public.orders" 比较。"""
    investigation = _collect_with(_CollectorConnection(regclass="orders"), monkeypatch)

    assert investigation is not None
    assert investigation.missing_index is not None
    assert investigation.missing_index.table == "orders"
    assert investigation.confidence == 1.0
    assert investigation.risks != []


def test_收集器在目标表不存在时无信号(monkeypatch: object) -> None:
    """to_regclass 解析不到对象才代表表不存在。"""
    assert _collect_with(_CollectorConnection(regclass=None), monkeypatch) is None


def test_收集器在索引已存在时无信号(monkeypatch: object) -> None:
    assert _collect_with(_CollectorConnection(index_exists=True), monkeypatch) is None


def test_收集器在无顺序扫描时无信号(monkeypatch: object) -> None:
    assert _collect_with(_CollectorConnection(seq_scan=False), monkeypatch) is None
