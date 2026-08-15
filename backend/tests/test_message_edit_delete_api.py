"""P8 消息编辑与删除——会话消息更正的 API 测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import V1Services
from src.application.contracts import CreateRunCommand, DiagnosisExecutionEvent, DiagnosisExecutionResult
from src.application.message_editing import MessageEditingApplicationService
from src.application.plain_messages import PlainMessageApplicationService
from src.application.services import RunApplicationService, SessionApplicationService
from src.domain.diagnosis import RunEventType, RunStatus
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import create_persistence_runtime
from src.infrastructure.persistence.message_editing_writer import SqlAlchemyMessageEditingWriter
from src.infrastructure.persistence.plain_message_writer import SqlAlchemyPlainMessageWriter

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


class _DeterministicExecutor:
    """不访问真实 Agent、只输出一条安全事件的确定性执行器。"""

    def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        yield DiagnosisExecutionEvent(
            type=RunEventType.ROUTE_DECIDED,
            node="route",
            occurred_at=datetime.now(UTC),
        )
        yield DiagnosisExecutionResult(strategy="direct")


def _upgrade_temporary_database(database_path: Path) -> None:
    """只通过 Alembic 在临时 SQLite 文件创建 schema（含本工作包迁移）。"""
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": os.pathsep.join((str(BACKEND_ROOT), str(PROJECT_ROOT))),
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.fixture
def v1_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """以迁移后的临时 SQLite 装配含消息编辑/删除服务的 v1 客户端。"""
    database_path = tmp_path / "p8-message-edit-delete.sqlite3"
    _upgrade_temporary_database(database_path)
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    services = V1Services(
        session_factory=runtime.session_factory,
        session_service=SessionApplicationService(runtime.session_factory),
        run_service=RunApplicationService(
            runtime.session_factory,
            _DeterministicExecutor(),
            ConservativeResultAssembler(),
        ),
        plain_message_service=PlainMessageApplicationService(SqlAlchemyPlainMessageWriter(runtime.session_factory)),
        message_editing_service=MessageEditingApplicationService(
            SqlAlchemyMessageEditingWriter(runtime.session_factory)
        ),
    )

    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client
    runtime.engine.dispose()


def _create_session(client: TestClient, title: str = "P8 消息编辑删除会话") -> dict[str, object]:
    response = client.post("/api/v1/sessions", json={"title": title})
    assert response.status_code == 201
    return response.json()["session"]


def _send_plain(client: TestClient, session_id: str, content: str) -> dict[str, object]:
    response = client.post(f"/api/v1/sessions/{session_id}/messages", json={"content": content})
    assert response.status_code == 201
    return response.json()


def _list_messages(client: TestClient, session_id: str) -> list[dict[str, object]]:
    response = client.get(f"/api/v1/sessions/{session_id}/messages")
    assert response.status_code == 200
    return response.json()["items"]


def test_编辑user消息返回更新后内容与edited_at且时间线不变(v1_client: TestClient) -> None:
    """AC1：PATCH 更新 user 消息，返回含 edited_at 的资源，created_at 与时间线位置不变。"""
    session = _create_session(v1_client)
    payload = _send_plain(v1_client, session["id"], "你好")
    message_id = payload["user_message"]["id"]
    original_created_at = payload["user_message"]["created_at"]

    response = v1_client.patch(
        f"/api/v1/sessions/{session['id']}/messages/{message_id}",
        json={"content": "你好，更正后的内容"},
    )

    assert response.status_code == 200
    updated = response.json()["message"]
    assert updated["id"] == message_id
    assert updated["content"] == "你好，更正后的内容"
    assert updated["created_at"] == original_created_at
    assert updated["edited_at"] is not None
    assert updated["edited_at"] >= original_created_at

    messages = _list_messages(v1_client, session["id"])
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "你好，更正后的内容"
    assert messages[0]["edited_at"] is not None
    assert messages[1]["edited_at"] is None


def test_编辑assistant消息返回422且消息不变(v1_client: TestClient) -> None:
    """AC2：编辑 assistant / system 消息返回明确错误（422），消息保留。"""
    session = _create_session(v1_client)
    payload = _send_plain(v1_client, session["id"], "谢谢")
    assistant_id = payload["assistant_message"]["id"]
    assistant_content = payload["assistant_message"]["content"]

    response = v1_client.patch(
        f"/api/v1/sessions/{session['id']}/messages/{assistant_id}",
        json={"content": "篡改回答"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MESSAGE_NOT_EDITABLE"
    messages = _list_messages(v1_client, session["id"])
    assert messages[1]["content"] == assistant_content
    assert messages[1]["edited_at"] is None


def test_编辑不存在的消息或不属于该会话返回404(v1_client: TestClient) -> None:
    """AC3：消息不存在 / 消息不属于该会话 → 404。"""
    session = _create_session(v1_client)
    other_session = _create_session(v1_client, title="另一个会话")
    payload = _send_plain(v1_client, other_session["id"], "你好")

    missing = v1_client.patch(
        f"/api/v1/sessions/{session['id']}/messages/{uuid4()}",
        json={"content": "新内容"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "MESSAGE_NOT_FOUND"

    foreign = v1_client.patch(
        f"/api/v1/sessions/{session['id']}/messages/{payload['user_message']['id']}",
        json={"content": "新内容"},
    )
    assert foreign.status_code == 404
    assert foreign.json()["error"]["code"] == "MESSAGE_NOT_FOUND"


def test_编辑空内容或超长内容返回422(v1_client: TestClient) -> None:
    """AC4：空内容 / 纯空白 / 超长内容 → 422。"""
    session = _create_session(v1_client)
    payload = _send_plain(v1_client, session["id"], "你好")
    message_id = payload["user_message"]["id"]

    empty = v1_client.patch(
        f"/api/v1/sessions/{session['id']}/messages/{message_id}",
        json={"content": "   "},
    )
    assert empty.status_code == 422

    too_long = v1_client.patch(
        f"/api/v1/sessions/{session['id']}/messages/{message_id}",
        json={"content": "长" * 4001},
    )
    assert too_long.status_code == 422

    messages = _list_messages(v1_client, session["id"])
    assert messages[0]["content"] == "你好"
    assert messages[0]["edited_at"] is None


def test_删除user消息返回204且列表不再出现(v1_client: TestClient) -> None:
    """AC5：DELETE user 消息 → 204，且消息不再出现在会话消息列表。"""
    session = _create_session(v1_client)
    payload = _send_plain(v1_client, session["id"], "发错了")
    message_id = payload["user_message"]["id"]

    response = v1_client.delete(f"/api/v1/sessions/{session['id']}/messages/{message_id}")

    assert response.status_code == 204
    messages = _list_messages(v1_client, session["id"])
    assert all(item["id"] != message_id for item in messages)


def test_删除assistant消息返回422且消息保留(v1_client: TestClient) -> None:
    """AC6：DELETE assistant / system 消息 → 422，消息保留。"""
    session = _create_session(v1_client)
    payload = _send_plain(v1_client, session["id"], "谢谢")
    assistant_id = payload["assistant_message"]["id"]

    response = v1_client.delete(f"/api/v1/sessions/{session['id']}/messages/{assistant_id}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MESSAGE_NOT_DELETABLE"
    messages = _list_messages(v1_client, session["id"])
    assert any(item["id"] == assistant_id for item in messages)


def test_删除与Run关联的消息不影响Run详情与历史留痕(v1_client: TestClient) -> None:
    """AC7：删除 Run 输入消息后，Run 详情仍可追溯、执行链路仍能读取软删除的输入消息。"""
    from src import app as api_module

    services = api_module.app.state.v1_services
    session = _create_session(v1_client)
    # 不经 HTTP 受理 Run（避免后台自动执行），以便先删除输入消息再走执行链路。
    accepted = services.run_service.accept_run(
        CreateRunCommand(
            session_id=session["id"],
            query="检查 CPU",
            idempotency_key=uuid4(),
            service_id=None,
        )
    )
    run_id = accepted.run.id
    input_message_id = accepted.run.input_message_id

    # 删除 Run 的输入消息：软删除成功，Run 记录不动。
    delete_response = v1_client.delete(f"/api/v1/sessions/{session['id']}/messages/{input_message_id}")
    assert delete_response.status_code == 204

    # 执行链路（_claim_run）仍能读取软删除的输入消息——这是历史可追溯的硬保证。
    completed = services.run_service.execute_run(run_id)
    assert completed.status == RunStatus.SUCCEEDED

    # Run 详情仍可追溯（input_message_id 关联不变）。
    detail = v1_client.get(f"/api/v1/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["run"]["input_message_id"] == str(input_message_id)
    assert detail.json()["run"]["status"] == "succeeded"


def test_重复删除同一消息幂等返回204(v1_client: TestClient) -> None:
    """AC8：重复删除同一消息 → 幂等 204，不产生错误副作用。"""
    session = _create_session(v1_client)
    payload = _send_plain(v1_client, session["id"], "发错了")
    message_id = payload["user_message"]["id"]

    first = v1_client.delete(f"/api/v1/sessions/{session['id']}/messages/{message_id}")
    second = v1_client.delete(f"/api/v1/sessions/{session['id']}/messages/{message_id}")

    assert first.status_code == 204
    assert second.status_code == 204
    assert _list_messages(v1_client, session["id"]) == []


def test_删除user消息时成对普通回复随删(v1_client: TestClient) -> None:
    """决策3：删除 user 消息时，其成对的无 Run 普通回复不再展示；后续消息不受影响。"""
    session = _create_session(v1_client)
    first = _send_plain(v1_client, session["id"], "第一条")
    second = _send_plain(v1_client, session["id"], "第二条")
    first_user_id = first["user_message"]["id"]
    first_reply_id = first["assistant_message"]["id"]
    second_user_id = second["user_message"]["id"]
    second_reply_id = second["assistant_message"]["id"]

    response = v1_client.delete(f"/api/v1/sessions/{session['id']}/messages/{first_user_id}")

    assert response.status_code == 204
    remaining = _list_messages(v1_client, session["id"])
    remaining_ids = [item["id"] for item in remaining]
    assert first_user_id not in remaining_ids
    assert first_reply_id not in remaining_ids
    # 第二条消息对完整保留且顺序不变。
    assert remaining_ids == [second_user_id, second_reply_id]


def test_删除与Run关联的消息其assistant输出不随删(v1_client: TestClient) -> None:
    """决策3：Run 关联的 assistant 输出（有 run_id）绝不随输入消息删除。"""
    session = _create_session(v1_client)
    run_response = v1_client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={"query": "检查 CPU"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert run_response.status_code == 202
    run = run_response.json()["run"]
    input_message_id = run["input_message_id"]

    delete_response = v1_client.delete(f"/api/v1/sessions/{session['id']}/messages/{input_message_id}")
    assert delete_response.status_code == 204

    remaining = _list_messages(v1_client, session["id"])
    # 输入消息不再展示；Run 关联的 assistant 输出（run_id 非空）保留可追溯。
    assert all(item["id"] != input_message_id for item in remaining)
    assert any(item["run_id"] == run["id"] for item in remaining)


def test_已删除消息再编辑返回404(v1_client: TestClient) -> None:
    """决策5：已删除消息 PATCH → 404（与「不存在」同语义）。"""
    session = _create_session(v1_client)
    payload = _send_plain(v1_client, session["id"], "发错了")
    message_id = payload["user_message"]["id"]
    v1_client.delete(f"/api/v1/sessions/{session['id']}/messages/{message_id}")

    response = v1_client.patch(
        f"/api/v1/sessions/{session['id']}/messages/{message_id}",
        json={"content": "新内容"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MESSAGE_NOT_FOUND"


def test_编辑已产生Run的输入消息不触发重跑且Run仍可追溯(v1_client: TestClient) -> None:
    """决策4：编辑 Run 输入消息仅改展示，不重跑；Run 关联与详情不变。"""
    session = _create_session(v1_client)
    run_response = v1_client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={"query": "检查 CPU"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert run_response.status_code == 202
    run = run_response.json()["run"]
    input_message_id = run["input_message_id"]

    edit_response = v1_client.patch(
        f"/api/v1/sessions/{session['id']}/messages/{input_message_id}",
        json={"content": "排查慢查询（更正措辞）"},
    )
    assert edit_response.status_code == 200
    assert edit_response.json()["message"]["edited_at"] is not None

    runs = v1_client.get(f"/api/v1/sessions/{session['id']}/runs").json()["items"]
    assert [item["id"] for item in runs] == [run["id"]]
    detail = v1_client.get(f"/api/v1/runs/{run['id']}")
    assert detail.status_code == 200
    assert detail.json()["run"]["input_message_id"] == input_message_id


def test_编辑删除接口不触碰Run结果与证据(v1_client: TestClient) -> None:
    """安全边界：编辑/删除后 Run 结果仍可读，接口响应不含证据原文外的任何字段。"""
    session = _create_session(v1_client)
    run_response = v1_client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        json={"query": "检查 CPU"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    run = run_response.json()["run"]
    input_message_id = run["input_message_id"]

    edit_response = v1_client.patch(
        f"/api/v1/sessions/{session['id']}/messages/{input_message_id}",
        json={"content": "排查慢查询（已更正）"},
    )
    assert edit_response.status_code == 200
    assert set(edit_response.json()["message"].keys()) <= {
        "id", "session_id", "run_id", "role", "content", "created_at", "edited_at",
    }
    assert v1_client.get(f"/api/v1/runs/{run['id']}").status_code == 200
