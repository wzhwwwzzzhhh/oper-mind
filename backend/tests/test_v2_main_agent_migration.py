"""V2 主 Agent 增量迁移的 upgrade／downgrade 数据安全证据。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.exc import IntegrityError

from src.infrastructure.persistence.database import create_app_engine

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
PREVIOUS_REVISION = "20260905_16_p14_role_models"
NEW_HEAD = "20261015_17_v2_main_delivery"


def _environment(database_path: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
            "PYTHONPATH": os.pathsep.join((str(BACKEND_ROOT), str(PROJECT_ROOT))),
        }
    )
    return environment


def _alembic(database_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
        cwd=database_path.parent,
        env=_environment(database_path),
        check=False,
        capture_output=True,
        text=True,
    )


def _scalar(database_path: Path, statement: str):
    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            return connection.exec_driver_sql(statement).scalar()
    finally:
        engine.dispose()


def _rows(database_path: Path, statement: str):
    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            return connection.exec_driver_sql(statement).all()
    finally:
        engine.dispose()


def _insert_legacy_rows(database_path: Path) -> tuple[str, str]:
    """写入带重跑来源的历史 Run，覆盖 batch 重建时的自引用外键。"""
    session_id = str(uuid4())
    now = "2026-08-12T00:00:00+00:00"
    original_message = str(uuid4())
    rerun_message = str(uuid4())
    original_run = str(uuid4())
    rerun_run = str(uuid4())
    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, "迁移历史", "active", now, now),
            )
            for message_id in (original_message, rerun_message):
                connection.exec_driver_sql(
                    "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, 'user', ?, ?)",
                    (message_id, session_id, "订单服务变慢。", now),
                )
            connection.exec_driver_sql(
                "INSERT INTO diagnosis_runs "
                "(id, session_id, trace_id, input_message_id, status, next_event_sequence, created_at) "
                "VALUES (?, ?, ?, ?, 'succeeded', 2, ?)",
                (original_run, session_id, str(uuid4()), original_message, now),
            )
            connection.exec_driver_sql(
                "INSERT INTO diagnosis_runs "
                "(id, session_id, trace_id, input_message_id, status, next_event_sequence, rerun_of_run_id, created_at) "
                "VALUES (?, ?, ?, ?, 'queued', 2, ?, ?)",
                (rerun_run, session_id, str(uuid4()), rerun_message, original_run, now),
            )
    finally:
        engine.dispose()
    return original_run, rerun_run


def _insert_main_run(database_path: Path, status: str = "queued") -> str:
    session_id = str(uuid4())
    message_id = str(uuid4())
    run_id = str(uuid4())
    now = "2026-10-15T00:00:00+00:00"
    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, "主 Agent 迁移", "active", now, now),
            )
            connection.exec_driver_sql(
                "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, 'user', ?, ?)",
                (message_id, session_id, "请比较两段文本", now),
            )
            connection.exec_driver_sql(
                "INSERT INTO diagnosis_runs "
                "(id, session_id, trace_id, input_message_id, runtime_kind, status, next_event_sequence, created_at) "
                "VALUES (?, ?, ?, ?, 'main_agent', ?, 2, ?)",
                (run_id, session_id, str(uuid4()), message_id, status, now),
            )
    finally:
        engine.dispose()
    return run_id


def test_upgrade_on_populated_database_backfills_diagnosis_and_keeps_rerun(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "v2-upgrade.sqlite3"
    assert _alembic(database_path, "upgrade", PREVIOUS_REVISION).returncode == 0
    original_run, rerun_run = _insert_legacy_rows(database_path)

    upgrade = _alembic(database_path, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr

    assert set(
        _rows(
            database_path,
            "SELECT id, runtime_kind, rerun_of_run_id FROM diagnosis_runs",
        )
    ) == {
        (original_run, "diagnosis", None),
        (rerun_run, "diagnosis", original_run),
    }
    legacy_snapshot = _scalar(database_path, "SELECT COUNT(*) FROM run_inputs")
    legacy_delivery = _scalar(database_path, "SELECT COUNT(*) FROM run_deliveries")
    assert (legacy_snapshot, legacy_delivery) == (0, 0)
    assert _scalar(database_path, "SELECT version_num FROM alembic_version") == NEW_HEAD

    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE diagnosis_runs SET runtime_kind = 'unsupported' WHERE id = ?",
                (original_run,),
            )
    finally:
        engine.dispose()


def test_downgrade_without_v2_data_preserves_legacy_rows_and_reupgrades(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "v2-downgrade-empty.sqlite3"
    assert _alembic(database_path, "upgrade", "head").returncode == 0
    original_run, rerun_run = _insert_legacy_rows(database_path)

    downgrade = _alembic(database_path, "downgrade", PREVIOUS_REVISION)
    assert downgrade.returncode == 0, downgrade.stderr
    assert set(_rows(database_path, "SELECT id, rerun_of_run_id FROM diagnosis_runs")) == {
        (original_run, None),
        (rerun_run, original_run),
    }
    assert _scalar(database_path, "SELECT version_num FROM alembic_version") == PREVIOUS_REVISION
    columns = {row[1] for row in _rows(database_path, "PRAGMA table_info(diagnosis_runs)")}
    assert "runtime_kind" not in columns
    tables = {row[0] for row in _rows(database_path, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert "run_inputs" not in tables
    assert "run_deliveries" not in tables

    reupgrade = _alembic(database_path, "upgrade", "head")
    assert reupgrade.returncode == 0, reupgrade.stderr
    assert set(_rows(database_path, "SELECT id, runtime_kind FROM diagnosis_runs")) == {
        (original_run, "diagnosis"),
        (rerun_run, "diagnosis"),
    }


def test_downgrade_refuses_when_main_agent_run_exists(tmp_path: Path) -> None:
    database_path = tmp_path / "v2-downgrade-main.sqlite3"
    assert _alembic(database_path, "upgrade", "head").returncode == 0
    run_id = _insert_main_run(database_path)

    downgrade = _alembic(database_path, "downgrade", PREVIOUS_REVISION)
    assert downgrade.returncode != 0
    assert "拒绝不安全回滚" in downgrade.stderr
    assert _scalar(database_path, "SELECT version_num FROM alembic_version") == NEW_HEAD
    assert _rows(
        database_path,
        f"SELECT id, runtime_kind, status FROM diagnosis_runs WHERE id = '{run_id}'",
    ) == [(run_id, "main_agent", "queued")]


def test_downgrade_refuses_when_only_run_inputs_exists(tmp_path: Path) -> None:
    database_path = tmp_path / "v2-downgrade-input.sqlite3"
    assert _alembic(database_path, "upgrade", "head").returncode == 0
    original_run, _ = _insert_legacy_rows(database_path)
    payload = json.dumps(
        {"schema_version": 1, "query": "请比较两段文本", "rule_version": "literal-lines@1"},
        ensure_ascii=False,
    )
    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "INSERT INTO run_inputs (run_id, schema_version, payload, created_at) VALUES (?, 1, ?, ?)",
                (original_run, payload, "2026-10-15T00:00:00+00:00"),
            )
    finally:
        engine.dispose()

    downgrade = _alembic(database_path, "downgrade", PREVIOUS_REVISION)
    assert downgrade.returncode != 0
    assert "拒绝不安全回滚" in downgrade.stderr
    assert _scalar(database_path, "SELECT version_num FROM alembic_version") == NEW_HEAD
    assert _scalar(database_path, "SELECT COUNT(*) FROM run_inputs") == 1


def test_alembic_v2_head_is_unique() -> None:
    config = Config(str(ALEMBIC_INI))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == [NEW_HEAD]
    assert len(NEW_HEAD) <= 32
