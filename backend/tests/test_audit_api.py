"""P8 审计操作记录 API 测试：跨服务跨会话活动检索、过滤、脱敏与回归。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
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
from src.infrastructure.persistence.models import SessionRecord
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisResultRepository,
    SqlAlchemyDiagnosisRunRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemySessionRepository,
)

T0 = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 8, 1, 1, 0, 0, tzinfo=UTC)
T2 = datetime(2026, 8, 2, 0, 0, 0, tzinfo=UTC)
T3 = datetime(2026, 8, 3, 0, 0, 0, tzinfo=UTC)
T4 = datetime(2026, 8, 4, 0, 0, 0, tzinfo=UTC)

ACTION_ID = "postgres.orders_compound_index_rebuild.v1"


def _digest() -> str:
    """构造合法的 64 位 action_digest。"""
    return sha256(b"audit-test").hexdigest()


def _coordinator_factory(_service_id: str | None = None):
    """审计测试不触发多 Agent 内核的占位工厂。"""
    raise AssertionError("审计测试不应触发 Coordinator 构造。")


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """以临时 SQLite 构建完整装配的 v1 API 客户端。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")

    database_path = tmp_path / "audit.sqlite3"
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
    existing_session: SessionData | None = None,
) -> tuple[UUID, UUID]:
    """种一条完整审计链（会话 → 消息 → Run → 可选结果/提案/事件），返回 (run_id, session_id)。

    `existing_session` 传入时复用既有会话（同会话多 Run 场景），否则新建会话。
    """
    session_data = (
        existing_session
        if existing_session is not None
        else SessionData(
            title=title,
            service_id=session_service_id,
            created_at=created_at,
            updated_at=created_at,
        )
    )
    db_session = session_factory()
    try:
        if existing_session is None or db_session.get(SessionRecord, session_data.id) is None:
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


def test_跨服务跨会话返回审计活动分页列表(api_client: TestClient) -> None:
    """AC1：统一审计流按时间倒序归并 Run 与 action 事件。"""
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

    response = api_client.get("/api/v1/audit/activities")

    assert response.status_code == 200
    body = response.json()
    assert body["page"]["has_more"] is False
    items = body["items"]
    assert [item["type"] for item in items] == ["proposal_created", "run_failed", "run_completed"]
    action_item = items[0]
    assert action_item["kind"] == "action"
    assert action_item["service_id"] == "redis-production"
    assert action_item["session_title"] == "会话B"
    assert action_item["outcome"] == "pending_approval"
    assert action_item["action_id"] == ACTION_ID
    assert action_item["mode"] == "target"
    assert action_item["proposal_id"] is not None
    assert action_item["approval_actor"] is None
    run_item = items[2]
    assert run_item["kind"] == "run"
    assert run_item["run_id"] == run_item["id"]
    assert run_item["service_id"] == "postgres-production"
    assert run_item["session_title"] == "会话A"
    assert run_item["outcome"] == "succeeded"
    assert run_item["summary"] == "慢查询结论A"
    assert run_item["severity"] == "high"


def test_时间窗过滤(api_client: TestClient) -> None:
    """AC2：from/to 只返回窗口内活动；from 晚于 to 返回 422。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="早期",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
    )
    _seed_run(
        services.session_factory,
        title="晚期",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T2,
    )

    response = api_client.get(
        "/api/v1/audit/activities",
        params={"from": T1.isoformat(), "to": T3.isoformat()},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["session_title"] for item in items] == ["晚期"]

    bad = api_client.get(
        "/api/v1/audit/activities",
        params={"from": T2.isoformat(), "to": T1.isoformat()},
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"


def test_服务过滤与未知服务空列表(api_client: TestClient) -> None:
    """AC3：service_id 只返回该服务活动；未知 ID 返回空列表不抛错。"""
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

    response = api_client.get("/api/v1/audit/activities", params={"service_id": "postgres-production"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert all(item["service_id"] == "postgres-production" for item in items)
    assert [item["session_title"] for item in items] == ["生产"]

    unknown = api_client.get("/api/v1/audit/activities", params={"service_id": "not-exist"})
    assert unknown.status_code == 200
    assert unknown.json()["items"] == []


def test_类型过滤覆盖Run与action两类(api_client: TestClient) -> None:
    """AC4：action_type 过滤只返回匹配类型；瞬时事件与非法值 422。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="完成",
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

    runs_only = api_client.get("/api/v1/audit/activities", params={"action_type": "run_completed"})
    assert runs_only.status_code == 200
    assert [item["type"] for item in runs_only.json()["items"]] == ["run_completed"]

    actions_only = api_client.get("/api/v1/audit/activities", params={"action_type": "approval_recorded"})
    assert actions_only.status_code == 200
    assert [item["type"] for item in actions_only.json()["items"]] == ["approval_recorded"]

    transitory = api_client.get("/api/v1/audit/activities", params={"action_type": "execution_requested"})
    assert transitory.status_code == 422

    invalid = api_client.get("/api/v1/audit/activities", params={"action_type": "not-a-type"})
    assert invalid.status_code == 422


def test_结果过滤(api_client: TestClient) -> None:
    """AC5：result 过滤覆盖固定映射与 data.status 派生（approved/expired）。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="成功Run",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
    )
    _seed_run(
        services.session_factory,
        title="动作闭环",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T1,
        proposal_status=ActionProposalStatus.VERIFIED,
        events=[
            (
                ActionEventType.EXECUTION_COMPLETED,
                T2,
                {"status": "succeeded", "mode": "target", "summary": "固定索引已重建。"},
            ),
            (
                ActionEventType.ACTION_FAILED,
                T3,
                {"status": "expired", "mode": "target", "summary": "批准已过期，未执行固定修复。"},
            ),
        ],
    )
    _seed_run(
        services.session_factory,
        title="过期提案",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.FAILED,
        created_at=T4,
    )

    succeeded = api_client.get("/api/v1/audit/activities", params={"result": "succeeded"})
    assert succeeded.status_code == 200
    assert [item["type"] for item in succeeded.json()["items"]] == [
        "execution_completed",
        "run_completed",
        "run_completed",
    ]

    expired = api_client.get("/api/v1/audit/activities", params={"result": "expired"})
    assert expired.status_code == 200
    assert [item["type"] for item in expired.json()["items"]] == ["action_failed"]

    invalid = api_client.get("/api/v1/audit/activities", params={"result": "not-a-result"})
    assert invalid.status_code == 422


def test_类型与结果组合过滤取交集(api_client: TestClient) -> None:
    """AC4/AC5 组合：action_type 与 result 同传时取交集；无交集返回空列表。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="被拦截",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
        proposal_status=ActionProposalStatus.BLOCKED,
        events=[
            (
                ActionEventType.ACTION_BLOCKED,
                T0,
                {"status": "blocked", "mode": "target", "summary": "前置条件不满足，动作被拦截。"},
            )
        ],
    )

    intersect = api_client.get(
        "/api/v1/audit/activities",
        params={"action_type": "action_blocked", "result": "blocked"},
    )
    assert intersect.status_code == 200
    assert [item["type"] for item in intersect.json()["items"]] == ["action_blocked"]

    disjoint = api_client.get(
        "/api/v1/audit/activities",
        params={"action_type": "action_blocked", "result": "approved"},
    )
    assert disjoint.status_code == 200
    assert disjoint.json()["items"] == []


def test_瞬时事件不入流且事件data非白名单字段不透传(api_client: TestClient) -> None:
    """AC6 边界：瞬时事件不入审计流；事件 data 非白名单字段绝不进入响应。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="闭环",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
        proposal_status=ActionProposalStatus.VERIFIED,
        events=[
            (
                ActionEventType.EXECUTION_REQUESTED,
                T1,
                {"status": "executing", "mode": "target", "summary": "已确认执行固定修复。"},
            ),
            (
                ActionEventType.EXECUTION_COMPLETED,
                T2,
                {
                    "status": "succeeded",
                    "mode": "target",
                    "summary": "固定索引已重建。",
                    "secret_field": "sk-leak-test",
                    "evidence": [{"sql": "SELECT * FROM orders"}],
                },
            ),
        ],
    )

    response = api_client.get("/api/v1/audit/activities")

    assert response.status_code == 200
    assert [item["type"] for item in response.json()["items"]] == ["execution_completed", "run_completed"]
    assert "sk-leak-test" not in response.text
    assert "secret_field" not in response.text
    assert "SELECT * FROM orders" not in response.text


def test_审批人字段如实标注未记录(api_client: TestClient) -> None:
    """AC7：approval_recorded 项 approval_actor="未记录"，决策与时间如实展示。"""
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

    response = api_client.get("/api/v1/audit/activities", params={"action_type": "approval_recorded"})

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["approval_actor"] == "未记录"
    assert item["outcome"] == "approved"
    assert item["occurred_at"] == T1.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    assert item["action_id"] is None
    assert item["mode"] is None


def test_无匹配记录返回空列表(api_client: TestClient) -> None:
    """AC8：空库与无匹配过滤均返回空列表，不抛错。"""
    empty = api_client.get("/api/v1/audit/activities")
    assert empty.status_code == 200
    assert empty.json()["items"] == []
    assert empty.json()["page"]["has_more"] is False

    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="有数据",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
    )
    no_match = api_client.get(
        "/api/v1/audit/activities",
        params={"service_id": "postgres-production", "action_type": "verification_completed"},
    )
    assert no_match.status_code == 200
    assert no_match.json()["items"] == []


def test_无服务绑定Run计入审计流(api_client: TestClient) -> None:
    """决策4：service_id=null 的 Run 正常展示，服务过滤时排除。"""
    services = api_client.app.state.v1_services
    _seed_run(
        services.session_factory,
        title="无服务",
        session_service_id=None,
        run_service_id=None,
        status=RunStatus.SUCCEEDED,
        created_at=T0,
        summary="未绑定服务的调查",
        severity=DiagnosisSeverity.INFO,
    )
    _seed_run(
        services.session_factory,
        title="有服务",
        session_service_id="postgres-production",
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T1,
    )

    all_items = api_client.get("/api/v1/audit/activities").json()["items"]
    assert len(all_items) == 2
    assert [item["service_id"] for item in all_items] == ["postgres-production", None]

    filtered = api_client.get(
        "/api/v1/audit/activities", params={"service_id": "postgres-production"}
    ).json()["items"]
    assert [item["session_title"] for item in filtered] == ["有服务"]


def test_多服务会话按Run服务归属过滤(api_client: TestClient) -> None:
    """P6 语义：会话多服务、每服务一 Run 时按 Run 的 service_id 过滤。"""
    services = api_client.app.state.v1_services
    session = SessionData(
        title="多服务会话",
        service_id=None,
        service_ids=("postgres-production", "postgres-staging"),
        created_at=T0,
        updated_at=T0,
    )
    _seed_run(
        services.session_factory,
        title="多服务会话",
        session_service_id=None,
        run_service_id="postgres-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
        existing_session=session,
    )
    _seed_run(
        services.session_factory,
        title="多服务会话",
        session_service_id=None,
        run_service_id="postgres-staging",
        status=RunStatus.FAILED,
        created_at=T1,
        existing_session=session,
    )

    response = api_client.get("/api/v1/audit/activities", params={"service_id": "postgres-staging"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["service_id"] == "postgres-staging"
    assert items[0]["outcome"] == "failed"


def test_既有服务活动契约不变(api_client: TestClient) -> None:
    """AC9：GET /services/{id}/activities 行为与契约不变。"""
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

    response = api_client.get("/api/v1/services/postgres-production/activities")

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["run_status"] == "succeeded"
    assert items[0]["summary"] == "慢查询结论"


def test_分页游标跨页无重复无遗漏(api_client: TestClient) -> None:
    """AC1/分页：同秒多行（3 Run + 1 事件链 Run + 2 事件）按 (time, id) 键集跨页稳定。"""
    services = api_client.app.state.v1_services
    for index in range(3):
        _seed_run(
            services.session_factory,
            title=f"同秒Run{index}",
            session_service_id="postgres-production",
            run_service_id="postgres-production",
            status=RunStatus.SUCCEEDED,
            created_at=T0,
        )
    _seed_run(
        services.session_factory,
        title="同秒事件",
        session_service_id="redis-production",
        run_service_id="redis-production",
        status=RunStatus.SUCCEEDED,
        created_at=T0,
        proposal_status=ActionProposalStatus.APPROVED,
        events=[
            (
                ActionEventType.PROPOSAL_CREATED,
                T0,
                {"status": "pending_approval", "mode": "target", "summary": "已生成受控靶场固定动作提案。"},
            ),
            (
                ActionEventType.APPROVAL_RECORDED,
                T0,
                {"status": "approved", "summary": "本地操作者已批准固定修复。"},
            ),
        ],
    )

    seen: list[str] = []
    cursor: str | None = None
    while True:
        params: dict[str, object] = {"limit": 2}
        if cursor is not None:
            params["cursor"] = cursor
        body = api_client.get("/api/v1/audit/activities", params=params).json()
        page_items = body["items"]
        assert len(page_items) <= 2
        seen.extend(item["id"] for item in page_items)
        if not body["page"]["has_more"]:
            break
        assert body["page"]["next_cursor"] is not None
        cursor = body["page"]["next_cursor"]

    assert len(seen) == 6
    assert len(set(seen)) == 6


def test_非法游标返回400(api_client: TestClient) -> None:
    """游标无法解码时返回 400 INVALID_CURSOR。"""
    response = api_client.get("/api/v1/audit/activities", params={"cursor": "not-a-cursor"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CURSOR"


def test_分页大小越界返回422(api_client: TestClient) -> None:
    """limit 越界返回 422。"""
    too_small = api_client.get("/api/v1/audit/activities", params={"limit": 0})
    assert too_small.status_code == 422

    too_large = api_client.get("/api/v1/audit/activities", params={"limit": 101})
    assert too_large.status_code == 422
