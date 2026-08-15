"""P8 审计导出 API 测试：同构投影、过滤一致、空态、超限、脱敏、确定性与回归。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import build_v1_services_for_runtime
from src.domain.actions import ActionEventData, ActionEventType, ActionProposalData, ActionProposalStatus
from src.domain.diagnosis import DiagnosisSeverity, MessageRole, RunStatus
from src.domain.records import DiagnosisResultData, DiagnosisRunData, MessageData, SessionData
from src.infrastructure.persistence.action_repositories import (
    SqlAlchemyActionEventRepository,
    SqlAlchemyActionProposalRepository,
)
from src.infrastructure.persistence.database import Base, create_persistence_runtime
from src.infrastructure.persistence.models import DiagnosisRunRecord, MessageRecord, SessionRecord
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisResultRepository,
    SqlAlchemyDiagnosisRunRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemySessionRepository,
)

T0 = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 8, 1, 1, 0, 0, tzinfo=UTC)
T2 = datetime(2026, 8, 2, 0, 0, 0, tzinfo=UTC)

ACTION_ID = "postgres.orders_compound_index_rebuild.v1"

# 与 AuditActivityResource 一致的 18 字段表头（Design D2）。
CSV_HEADER = (
    "id,kind,type,occurred_at,service_id,session_id,session_title,outcome,summary,"
    "run_id,severity,confidence,proposal_status,verification_status,proposal_id,"
    "action_id,mode,approval_actor"
)


def _digest() -> str:
    """构造合法的 64 位 action_digest。"""
    return sha256(b"audit-export-test").hexdigest()


def _coordinator_factory(_service_id: str | None = None):
    """审计导出测试不触发多 Agent 内核的占位工厂。"""
    raise AssertionError("审计导出测试不应触发 Coordinator 构造。")


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """以临时 SQLite 构建完整装配的 v1 API 客户端。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")

    database_path = tmp_path / "audit-export.sqlite3"
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(runtime.engine)
    services = build_v1_services_for_runtime(runtime, _coordinator_factory)
    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")

    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client
    runtime.engine.dispose()


def _seed_run(
    session_factory,
    *,
    title: str,
    session_service_id: str | None,
    run_service_id: str | None,
    status: RunStatus,
    created_at: datetime,
    summary: str | None = None,
    severity: DiagnosisSeverity | None = None,
    proposal_status: ActionProposalStatus | None = None,
    events: tuple[tuple[ActionEventType, datetime, dict[str, object]], ...] = (),
) -> tuple[UUID, UUID]:
    """种一条完整审计链（会话 → 消息 → Run → 可选结果/提案/事件），返回 (run_id, session_id)。"""
    session_data = SessionData(
        title=title,
        service_id=session_service_id,
        created_at=created_at,
        updated_at=created_at,
    )
    db_session = session_factory()
    try:
        SqlAlchemySessionRepository(db_session).add(session_data)
        db_session.flush()
        message = MessageData(
            session_id=session_data.id,
            role=MessageRole.USER,
            content="调查问题",
            created_at=created_at,
        )
        SqlAlchemyMessageRepository(db_session).add(message)
        db_session.flush()
        run = DiagnosisRunData(
            session_id=session_data.id,
            input_message_id=message.id,
            service_id=run_service_id,
            status=status,
            created_at=created_at,
            started_at=created_at if status is not RunStatus.QUEUED else None,
            finished_at=created_at if status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED) else None,
        )
        SqlAlchemyDiagnosisRunRepository(db_session).add(run)
        db_session.flush()
        if summary is not None and severity is not None:
            SqlAlchemyDiagnosisResultRepository(db_session).add(
                DiagnosisResultData(
                    run_id=run.id,
                    summary=summary,
                    severity=severity,
                    confidence=0.85,
                    root_causes=[],
                    evidence=[],
                    recommendations=[],
                    risks=[],
                    requires_approval=False,
                    agent_summary=[],
                    created_at=created_at,
                )
            )
        if proposal_status is not None:
            proposal = ActionProposalData(
                source_run_id=run.id,
                action_id=ACTION_ID,
                action_digest=_digest(),
                status=proposal_status,
                mode="target",
                title="重建受控靶场联合索引",
                description="只对受控靶场固定目标执行代码内联合索引动作。",
                target={"service_id": "postgres-target"},
                root_cause_id=uuid4(),
                evidence_ids=[uuid4(), uuid4(), uuid4()],
                risk_summary="受控靶场结构变更；生产和预发布实例不会执行。",
                verification_plan=["确认受控靶场目标表存在"],
                created_at=created_at,
                updated_at=created_at,
            )
            SqlAlchemyActionProposalRepository(db_session).add(proposal)
            db_session.flush()
            for sequence, (event_type, occurred_at, data) in enumerate(events, start=1):
                SqlAlchemyActionEventRepository(db_session).add(
                    ActionEventData(
                        proposal_id=proposal.id,
                        sequence=sequence,
                        type=event_type,
                        occurred_at=occurred_at,
                        data=data,
                    )
                )
        db_session.commit()
        return run.id, session_data.id
    finally:
        db_session.close()


def _seed_many_runs(session_factory, *, count: int, created_at: datetime) -> None:
    """批量种 count 条 Run（同一会话），用于超限边界测试。"""
    db_session = session_factory()
    try:
        session = SessionRecord(
            id=uuid4(),
            title="批量会话",
            service_id="postgres-production",
            created_at=created_at,
            updated_at=created_at,
        )
        db_session.add(session)
        db_session.flush()
        for index in range(count):
            message = MessageRecord(
                id=uuid4(),
                session_id=session.id,
                role="user",
                content=f"批量问题{index}",
                created_at=created_at,
            )
            db_session.add(message)
            db_session.flush()
            db_session.add(
                DiagnosisRunRecord(
                    id=uuid4(),
                    session_id=session.id,
                    trace_id=uuid4(),
                    input_message_id=message.id,
                    service_id="postgres-production",
                    status="succeeded",
                    created_at=created_at,
                    started_at=created_at,
                    finished_at=created_at,
                )
            )
        db_session.commit()
    finally:
        db_session.close()


def _export_csv(client: TestClient, **params: object) -> tuple[int, str, dict[str, str]]:
    """请求 CSV 导出，返回 (状态码, 响应文本, 响应头)。"""
    query: dict[str, object] = {"format": "csv"}
    for key, value in params.items():
        if value is None:
            continue
        # 测试参数 from_ 映射到接口的 from（FastAPI alias）。
        query["from" if key == "from_" else key] = value
    response = client.get("/api/v1/audit/export", params=query)
    return response.status_code, response.text, dict(response.headers)


def test_导出内容与列表同构且排序一致(api_client: TestClient) -> None:
    """AC1/AC8：CSV 表头为 18 字段同投影；行内容与列表同条件一致；时间倒序。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="会话A",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
        summary="慢查询结论A",
        severity=DiagnosisSeverity.HIGH,
    )
    _seed_run(
        services.session_factory,
        title="会话B",
        session_service_id="redis-production",
        run_service_id="redis-production",
        status=RunStatus.FAILED,
        created_at=T1,
        proposal_status=ActionProposalStatus.PENDING_APPROVAL,
        events=[
            (
                ActionEventType.PROPOSAL_CREATED,
                T2,
                {
                    "action_id": ACTION_ID,
                    "status": "pending_approval",
                    "mode": "target",
                    "summary": "已生成受控靶场固定动作提案。",
                },
            )
        ],
    )

    status, text, headers = _export_csv(api_client)
    assert status == 200
    assert headers["x-export-count"] == "3"
    assert "attachment" in headers["content-disposition"]
    assert text.splitlines()[0].startswith("# 导出时间")
    # 表头 18 字段同投影
    assert CSV_HEADER in text
    data_lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert data_lines[0] == CSV_HEADER
    rows = data_lines[1:]
    assert len(rows) == 3
    # 与列表同条件一致：类型倒序 proposal_created → run_failed → run_completed
    list_body = api_client.get("/api/v1/audit/activities").json()
    assert [item["type"] for item in list_body["items"]] == ["proposal_created", "run_failed", "run_completed"]
    assert rows[0].split(",")[2] == "proposal_created"
    assert rows[1].split(",")[2] == "run_failed"
    assert rows[2].split(",")[2] == "run_completed"
    # 导出行与列表资源同投影（id / session_title / summary）
    assert rows[2].split(",")[0] == list_body["items"][2]["id"]
    assert "会话A" in rows[2]
    assert "慢查询结论A" in rows[2]


def test_过滤条件与列表一致(api_client: TestClient) -> None:
    """AC2：service_id / action_type / result / from / to 过滤语义与列表一致。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="生产",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
    )
    _seed_run(
        services.session_factory,
        title="缓存",
        session_service_id="redis-production",
        run_service_id="redis-production",
        status=RunStatus.FAILED,
        created_at=T1,
    )

    status, text, headers = _export_csv(api_client, service_id="postgres-production")
    assert status == 200
    assert headers["x-export-count"] == "1"
    data_lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(data_lines) == 2  # 表头 + 1 行
    assert "生产" in data_lines[1]

    status, text, _ = _export_csv(api_client, result="succeeded")
    assert status == 200
    data_lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(data_lines) == 2
    assert "生产" in data_lines[1]

    status, text, _ = _export_csv(api_client, action_type="run_failed")
    assert status == 200
    data_lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(data_lines) == 2
    assert "缓存" in data_lines[1]

    status, text, headers = _export_csv(api_client, from_=T1.isoformat(), to=T2.isoformat())
    assert status == 200
    assert headers["x-export-count"] == "1"
    data_lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert "缓存" in data_lines[1]

    # 未知 service_id → 空导出，不抛错
    status, text, headers = _export_csv(api_client, service_id="not-exist")
    assert status == 200
    assert headers["x-export-count"] == "0"


def test_窗口不合法返回422(api_client: TestClient) -> None:
    """from 晚于 to 返回 422 VALIDATION_ERROR（与列表一致）。"""
    response = api_client.get(
        "/api/v1/audit/export",
        params={"from": T2.isoformat(), "to": T1.isoformat(), "format": "csv"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_空结果返回0条元信息空文件(api_client: TestClient) -> None:
    """AC3：无匹配记录返回 200 空文件（元信息 0 条 + 表头），不抛错。"""
    status, text, headers = _export_csv(api_client)
    assert status == 200
    assert headers["x-export-count"] == "0"
    assert "# 条数: 0" in text
    assert "# 说明: 只读快照，不含原始证据、工具输出与凭据" in text
    data_lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert data_lines == [CSV_HEADER]


def test_结果超过上限返回422明确提示(api_client: TestClient) -> None:
    """AC4：超过 5000 条返回 422 EXPORT_LIMIT_EXCEEDED，不返回截断文件。"""
    services = api_client.app.state.v1_services
    _seed_many_runs(services.session_factory, count=5001, created_at=T0)

    response = api_client.get("/api/v1/audit/export", params={"format": "csv"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "EXPORT_LIMIT_EXCEEDED"
    assert "5000" in error["message"]
    assert "收窄" in error["message"]

    # 收窄时间窗后可导出（确定性：只含窗口内记录）
    narrowed = T0 + timedelta(minutes=1)
    status, text, headers = _export_csv(api_client, from_=narrowed.isoformat(), to=T2.isoformat())
    assert status == 200
    assert headers["x-export-count"] == "0"


def test_边界恰5000条可导出(api_client: TestClient) -> None:
    """AC4 边界：恰 5000 条可完整导出。"""
    services = api_client.app.state.v1_services
    _seed_many_runs(services.session_factory, count=5000, created_at=T0)

    status, text, headers = _export_csv(api_client)
    assert status == 200
    assert headers["x-export-count"] == "5000"
    data_lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    assert len(data_lines) == 5001  # 表头 + 5000 行


def test_敏感字面量不进导出文件(api_client: TestClient) -> None:
    """AC5：summary/session_title 中的 sk-、键值凭据、URL 凭据段被兜底脱敏。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="凭据会话",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
        summary="连接串 postgres://user:secret@host:5432/db 与密钥 sk-abcdef123456 不应出现",
        severity=DiagnosisSeverity.HIGH,
    )

    status, text, _ = _export_csv(api_client)
    assert status == 200
    assert "sk-abcdef123456" not in text
    assert "sk-" not in text
    assert "user:secret" not in text
    assert "postgres://user" not in text
    assert "[已脱敏" in text


def test_审批人字段如实未记录(api_client: TestClient) -> None:
    """AC6：approval_recorded 项 approval_actor="未记录"；其他项为空。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="审批",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
        proposal_status=ActionProposalStatus.APPROVED,
        events=[
            (
                ActionEventType.APPROVAL_RECORDED,
                T1,
                {"status": "approved", "summary": "本地操作者已批准固定修复。"},
            )
        ],
    )

    status, text, _ = _export_csv(api_client, action_type="approval_recorded")
    assert status == 200
    row = [line for line in text.splitlines() if line and not line.startswith("#")][1]
    assert "未记录" in row
    assert "local_operator" not in text


def test_导出元信息四要素齐全(api_client: TestClient) -> None:
    """AC7：元信息含导出时间、过滤条件（未过滤项"无"）、条数、快照标注。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="留痕",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
    )

    status, text, _ = _export_csv(api_client, service_id="postgres-production")
    assert status == 200
    meta_lines = [line for line in text.splitlines() if line.startswith("#")]
    joined = "\n".join(meta_lines)
    assert "# 导出时间:" in joined
    assert "# 过滤条件:" in joined
    assert "service_id=postgres-production" in joined
    assert "from=无" in joined and "to=无" in joined
    assert "action_type=无" in joined and "result=无" in joined
    assert "# 条数: 1" in joined
    assert "# 说明: 只读快照，不含原始证据、工具输出与凭据" in joined


def test_相同条件重复导出内容一致(api_client: TestClient) -> None:
    """AC8：相同条件两次导出，除导出时间外内容一致（确定性）。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="确定性",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
    )

    _, first_text, _ = _export_csv(api_client)
    _, second_text, _ = _export_csv(api_client)

    def strip_time(value: str) -> str:
        return "\n".join(
            line for line in value.splitlines() if not line.startswith("# 导出时间")
        )

    assert strip_time(first_text) == strip_time(second_text)


def test_markdown格式导出(api_client: TestClient) -> None:
    """格式 md：元信息块 + 活动记录表格，0 条时为空表格说明。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="MD会话",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
    )

    response = api_client.get("/api/v1/audit/export", params={"format": "md"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["x-export-count"] == "1"
    assert "## 导出元信息" in response.text
    assert "## 活动记录" in response.text
    assert "MD会话" in response.text

    empty = api_client.get(
        "/api/v1/audit/export",
        params={"format": "md", "from": T2.isoformat()},
    )
    assert empty.status_code == 200
    assert empty.headers["x-export-count"] == "0"
    assert "无匹配记录" in empty.text


def test_非法格式返回422(api_client: TestClient) -> None:
    """format 非法值返回 422。"""
    response = api_client.get("/api/v1/audit/export", params={"format": "xlsx"})
    assert response.status_code == 422


def test_既有审计检索契约不变(api_client: TestClient) -> None:
    """AC10：GET /audit/activities 行为与契约不变（回归）。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="留痕",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
        summary="慢查询结论",
        severity=DiagnosisSeverity.HIGH,
    )

    response = api_client.get("/api/v1/audit/activities")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "run_completed"
    assert items[0]["summary"] == "慢查询结论"
