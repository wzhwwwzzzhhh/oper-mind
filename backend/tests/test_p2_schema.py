"""P2.2a 会话诊断 schema 的迁移与约束验证。"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from src.infrastructure.persistence import models
from src.infrastructure.persistence.database import Base, create_app_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
BUSINESS_TABLES = {
    "sessions",
    "session_services",
    "messages",
    "diagnosis_runs",
    "run_events",
    "diagnosis_results",
    "run_idempotency_keys",
    "action_proposals",
    "action_approvals",
    "action_executions",
    "action_verifications",
    "action_events",
    "action_idempotency_keys",
    "service_monitor_samples",
    "model_providers",
    "model_provider_idempotency_keys",
    "service_registry",
    "app_settings",
}
EXPECTED_TABLES = BUSINESS_TABLES | {"alembic_version"}


def _alembic_environment(database_path: Path) -> dict[str, str]:
    """构造独立临时 SQLite migration 的最小环境变量。"""
    environment = os.environ.copy()
    python_path = [str(BACKEND_ROOT), str(PROJECT_ROOT)]
    if current_python_path := environment.get("PYTHONPATH"):
        python_path.append(current_python_path)
    environment.update(
        {
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
            "PYTHONPATH": os.pathsep.join(python_path),
        }
    )
    return environment


def _run_alembic(
    command: list[str],
    database_path: Path,
    working_directory: Path,
    database_url: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """通过绝对 alembic.ini 路径在指定目录运行迁移命令。"""
    environment = _alembic_environment(database_path)
    if database_url is not None:
        environment["OPERMIND_APP_DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *command],
        cwd=working_directory,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _create_session_and_run(engine: Engine) -> tuple[str, str]:
    """插入满足 P2 外键链路的会话、输入消息和 Run。"""
    session_id = str(uuid4())
    input_message_id = str(uuid4())
    run_id = str(uuid4())
    now = datetime.now(UTC).isoformat()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO sessions (id, title, status, created_at, updated_at) "
                "VALUES (:id, :title, :status, :created_at, :updated_at)"
            ),
            {
                "id": session_id,
                "title": "P2 schema test",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        )
        connection.execute(
            text(
                "INSERT INTO messages (id, session_id, role, content, created_at) "
                "VALUES (:id, :session_id, :role, :content, :created_at)"
            ),
            {
                "id": input_message_id,
                "session_id": session_id,
                "role": "user",
                "content": "检查 schema 约束",
                "created_at": now,
            },
        )
        connection.execute(
            text(
                "INSERT INTO diagnosis_runs (id, session_id, trace_id, input_message_id, "
                "status, next_event_sequence, created_at) "
                "VALUES (:id, :session_id, :trace_id, :input_message_id, :status, "
                ":next_event_sequence, :created_at)"
            ),
            {
                "id": run_id,
                "session_id": session_id,
                "trace_id": str(uuid4()),
                "input_message_id": input_message_id,
                "status": "queued",
                "next_event_sequence": 1,
                "created_at": now,
            },
        )
    return session_id, run_id


def test_p2_schema_metadata_声明P2与P4业务表且不含循环外键() -> None:
    """ORM metadata 包含 P2 与 P4.2 业务表，messages.run_id 保持应用层引用。"""
    assert set(Base.metadata.tables) == BUSINESS_TABLES

    message_table = Base.metadata.tables["messages"]
    assert not message_table.c.run_id.foreign_keys
    assert {foreign_key.target_fullname for foreign_key in message_table.foreign_keys} == {"sessions.id"}
    assert {
        foreign_key.target_fullname
        for foreign_key in Base.metadata.tables["diagnosis_runs"].foreign_keys
    } == {"sessions.id", "messages.id"}


def test_p2_schema_alembic_fresh_db_约束降级与再次升级(tmp_path: Path) -> None:
    """P2/P4.2 migration 在临时库创建完整 schema，且可完整降级和再次升级。"""
    database_path = tmp_path / "p2-schema.sqlite3"
    outside_repository = tmp_path / "outside-repository"
    outside_repository.mkdir()

    result = _run_alembic(["upgrade", "head"], database_path, outside_repository)
    assert result.returncode == 0, result.stderr

    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == EXPECTED_TABLES

        assert inspector.get_foreign_keys("messages") == [
            {
                "name": "fk_messages_session_id_sessions",
                "constrained_columns": ["session_id"],
                "referred_schema": None,
                "referred_table": "sessions",
                "referred_columns": ["id"],
                "options": {"ondelete": "RESTRICT"},
            }
        ]
        assert {tuple(item["column_names"]) for item in inspector.get_unique_constraints("run_events")} == {
            ("run_id", "sequence")
        }
        assert {tuple(item["column_names"]) for item in inspector.get_unique_constraints("diagnosis_runs")} == {
            ("input_message_id",)
        }
        assert {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("run_idempotency_keys")
        } == {("session_id", "endpoint", "idempotency_key")}
        assert {item["name"] for item in inspector.get_check_constraints("diagnosis_runs")} == {
            "ck_diagnosis_runs_diagnosis_run_status_valid",
            "ck_diagnosis_runs_diagnosis_run_next_sequence_positive",
        }
        assert {item["name"] for item in inspector.get_check_constraints("diagnosis_results")} == {
            "ck_diagnosis_results_diagnosis_result_confidence_range",
            "ck_diagnosis_results_diagnosis_result_schema_version_positive",
            "ck_diagnosis_results_diagnosis_result_severity_valid",
        }
        assert {item["name"] for item in inspector.get_check_constraints("run_idempotency_keys")} == {
            "ck_run_idempotency_keys_run_idempotency_expiry_after_created"
        }
        assert {item["name"] for item in inspector.get_indexes("messages")} == {
            "ix_messages_run_id",
            "ix_messages_session_created_at_id",
        }
        session_columns = {item["name"]: item for item in inspector.get_columns("sessions")}
        assert session_columns["service_id"]["nullable"] is True
        # P8 决策 8：service_id CHECK 白名单已放宽，sessions 只保留状态约束。
        assert {item["name"] for item in inspector.get_check_constraints("sessions")} == {
            "ck_sessions_session_status_valid",
        }
        assert {item["name"] for item in inspector.get_indexes("sessions")} == {
            "ix_sessions_service_updated_at_id",
            "ix_sessions_updated_at_id",
        }
        assert {tuple(item["column_names"]) for item in inspector.get_unique_constraints("action_proposals")} == {
            ("source_run_id",)
        }
        assert {tuple(item["column_names"]) for item in inspector.get_unique_constraints("action_approvals")} == {
            ("proposal_id",)
        }
        assert {tuple(item["column_names"]) for item in inspector.get_unique_constraints("action_executions")} == {
            ("proposal_id",)
        }
        assert {tuple(item["column_names"]) for item in inspector.get_unique_constraints("action_verifications")} == {
            ("execution_id",)
        }
        assert {tuple(item["column_names"]) for item in inspector.get_unique_constraints("action_events")} == {
            ("proposal_id", "sequence")
        }
        assert {tuple(item["column_names"]) for item in inspector.get_unique_constraints("action_idempotency_keys")} == {
            ("proposal_id", "endpoint", "idempotency_key")
        }
    finally:
        engine.dispose()

    result = _run_alembic(["downgrade", "base"], database_path, outside_repository)
    assert result.returncode == 0, result.stderr
    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        assert inspect(engine).get_table_names() == ["alembic_version"]
    finally:
        engine.dispose()

    result = _run_alembic(["upgrade", "head"], database_path, outside_repository)
    assert result.returncode == 0, result.stderr
    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES
    finally:
        engine.dispose()


def test_p2_schema_sqlite_外键唯一与检查约束生效(tmp_path: Path) -> None:
    """SQLite 必须启用外键，并实际执行 P2 的唯一键和检查约束。"""
    database_path = tmp_path / "p2-constraints.sqlite3"
    result = _run_alembic(["upgrade", "head"], database_path, tmp_path)
    assert result.returncode == 0, result.stderr

    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

        session_id, run_id = _create_session_and_run(engine)
        now = datetime.now(UTC).isoformat()

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO messages (id, session_id, role, content, created_at) "
                    "VALUES (:id, :session_id, :role, :content, :created_at)"
                ),
                {
                    "id": str(uuid4()),
                    "session_id": str(uuid4()),
                    "role": "user",
                    "content": "不存在的会话",
                    "created_at": now,
                },
            )

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO run_events (id, run_id, sequence, type, occurred_at, data) "
                    "VALUES (:id, :run_id, :sequence, :type, :occurred_at, :data)"
                ),
                {
                    "id": str(uuid4()),
                    "run_id": run_id,
                    "sequence": 0,
                    "type": "run_queued",
                    "occurred_at": now,
                    "data": "{}",
                },
            )

        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO run_events (id, run_id, sequence, type, occurred_at, data) "
                    "VALUES (:id, :run_id, :sequence, :type, :occurred_at, :data)"
                ),
                {
                    "id": str(uuid4()),
                    "run_id": run_id,
                    "sequence": 1,
                    "type": "run_queued",
                    "occurred_at": now,
                    "data": "{}",
                },
            )

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO run_events (id, run_id, sequence, type, occurred_at, data) "
                    "VALUES (:id, :run_id, :sequence, :type, :occurred_at, :data)"
                ),
                {
                    "id": str(uuid4()),
                    "run_id": run_id,
                    "sequence": 1,
                    "type": "run_queued",
                    "occurred_at": now,
                    "data": "{}",
                },
            )

        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO diagnosis_results (id, run_id, schema_version, summary, severity, "
                    "confidence, root_causes, evidence, recommendations, risks, requires_approval, "
                    "agent_summary, created_at) VALUES (:id, :run_id, 1, :summary, :severity, "
                    ":confidence, :root_causes, :evidence, :recommendations, :risks, "
                    ":requires_approval, :agent_summary, :created_at)"
                ),
                {
                    "id": str(uuid4()),
                    "run_id": run_id,
                    "summary": "无效置信度",
                    "severity": "medium",
                    "confidence": 1.1,
                    "root_causes": "[]",
                    "evidence": "[]",
                    "recommendations": "[]",
                    "risks": "[]",
                    "requires_approval": False,
                    "agent_summary": "[]",
                    "created_at": now,
                },
            )

        created_at = datetime.now(UTC)
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO run_idempotency_keys (id, session_id, endpoint, idempotency_key, "
                    "request_fingerprint, run_id, expires_at, created_at) VALUES "
                    "(:id, :session_id, :endpoint, :idempotency_key, :request_fingerprint, :run_id, "
                    ":expires_at, :created_at)"
                ),
                {
                    "id": str(uuid4()),
                    "session_id": session_id,
                    "endpoint": "/api/v1/sessions/runs",
                    "idempotency_key": str(uuid4()),
                    "request_fingerprint": "a" * 64,
                    "run_id": run_id,
                    "expires_at": created_at.isoformat(),
                    "created_at": (created_at + timedelta(seconds=1)).isoformat(),
                },
            )
    finally:
        engine.dispose()


def test_p2_schema_postgresql_orm与迁移ddl可离线编译(tmp_path: Path) -> None:
    """不连接真实 PostgreSQL，仅验证 P2 ORM metadata 与 migration 离线 DDL。"""
    dialect = postgresql.dialect()
    ddl_by_table = {
        table.name: str(CreateTable(table).compile(dialect=dialect))
        for table in Base.metadata.sorted_tables
    }
    assert set(ddl_by_table) == BUSINESS_TABLES
    uuid_tables = {name for name in ddl_by_table if name != "app_settings"}
    assert all("UUID" in ddl for name, ddl in ddl_by_table.items() if name in uuid_tables)
    assert "VARCHAR(100)" in ddl_by_table["app_settings"]
    assert "FOREIGN KEY(session_id) REFERENCES sessions (id) ON DELETE RESTRICT" in ddl_by_table["messages"]
    assert "FOREIGN KEY(input_message_id) REFERENCES messages (id) ON DELETE RESTRICT" in ddl_by_table[
        "diagnosis_runs"
    ]

    result = _run_alembic(
        ["upgrade", "head", "--sql"],
        tmp_path / "unused.sqlite3",
        tmp_path,
        database_url="postgresql+psycopg://opermind:password@localhost/opermind",
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE sessions" in result.stdout
    assert "CREATE TABLE diagnosis_runs" in result.stdout
    assert "CREATE TABLE run_idempotency_keys" in result.stdout
    assert "CREATE TABLE action_proposals" in result.stdout
    assert "CREATE TABLE action_idempotency_keys" in result.stdout
    assert "UUID" in result.stdout
    assert "CONSTRAINT diagnosis_run_input_message_unique UNIQUE (input_message_id)" in result.stdout




def test_p2_schema_sqlite_受控状态与其余唯一约束生效(tmp_path: Path) -> None:
    """SQLite 实际拒绝受控状态之外的值及 P2 的其余唯一键冲突。"""
    database_path = tmp_path / "p2-controlled-values.sqlite3"
    result = _run_alembic(["upgrade", "head"], database_path, tmp_path)
    assert result.returncode == 0, result.stderr

    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        session_id, run_id = _create_session_and_run(engine)
        now = datetime.now(UTC).isoformat()
        with engine.connect() as connection:
            input_message_id = connection.execute(
                text("SELECT input_message_id FROM diagnosis_runs WHERE id = :run_id"),
                {"run_id": run_id},
            ).scalar_one()

        invalid_statements = [
            (
                "INSERT INTO messages (id, session_id, role, content, created_at) "
                "VALUES (:id, :session_id, :role, :content, :created_at)",
                {
                    "id": str(uuid4()),
                    "session_id": session_id,
                    "role": "operator",
                    "content": "无效角色",
                    "created_at": now,
                },
            ),
            (
                "INSERT INTO diagnosis_runs (id, session_id, trace_id, input_message_id, "
                "status, next_event_sequence, created_at) VALUES "
                "(:id, :session_id, :trace_id, :input_message_id, :status, "
                ":next_event_sequence, :created_at)",
                {
                    "id": str(uuid4()),
                    "session_id": session_id,
                    "trace_id": str(uuid4()),
                    "input_message_id": input_message_id,
                    "status": "retrying",
                    "next_event_sequence": 1,
                    "created_at": now,
                },
            ),
            (
                "INSERT INTO run_events (id, run_id, sequence, type, occurred_at, data) "
                "VALUES (:id, :run_id, :sequence, :type, :occurred_at, :data)",
                {
                    "id": str(uuid4()),
                    "run_id": run_id,
                    "sequence": 2,
                    "type": "tool_raw_output",
                    "occurred_at": now,
                    "data": "{}",
                },
            ),
            (
                "INSERT INTO diagnosis_results (id, run_id, schema_version, summary, severity, "
                "confidence, root_causes, evidence, recommendations, risks, requires_approval, "
                "agent_summary, created_at) VALUES (:id, :run_id, 1, :summary, :severity, "
                ":confidence, :root_causes, :evidence, :recommendations, :risks, "
                ":requires_approval, :agent_summary, :created_at)",
                {
                    "id": str(uuid4()),
                    "run_id": run_id,
                    "summary": "无效严重性",
                    "severity": "urgent",
                    "confidence": 0.5,
                    "root_causes": "[]",
                    "evidence": "[]",
                    "recommendations": "[]",
                    "risks": "[]",
                    "requires_approval": False,
                    "agent_summary": "[]",
                    "created_at": now,
                },
            ),
        ]
        for statement, parameters in invalid_statements:
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(text(statement), parameters)

        idempotency_key = str(uuid4())
        idempotency_parameters = {
            "session_id": session_id,
            "endpoint": "/api/v1/sessions/{session_id}/runs",
            "idempotency_key": idempotency_key,
            "request_fingerprint": "b" * 64,
            "run_id": run_id,
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "created_at": now,
        }
        statement = text(
            "INSERT INTO run_idempotency_keys (id, session_id, endpoint, idempotency_key, "
            "request_fingerprint, run_id, expires_at, created_at) VALUES "
            "(:id, :session_id, :endpoint, :idempotency_key, :request_fingerprint, :run_id, "
            ":expires_at, :created_at)"
        )
        with engine.begin() as connection:
            connection.execute(statement, {"id": str(uuid4()), **idempotency_parameters})
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(statement, {"id": str(uuid4()), **idempotency_parameters})
    finally:
        engine.dispose()


def test_p2_schema_utc_default为aware时间() -> None:
    """ORM 默认时间函数必须返回 UTC aware datetime。"""
    value = models.utc_now()

    assert value.tzinfo is UTC
    assert value.utcoffset() == timedelta(0)
