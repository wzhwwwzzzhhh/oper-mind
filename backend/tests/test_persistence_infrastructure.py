"""P1.1d 应用持久化基础设施测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from sqlalchemy import Column, Integer, MetaData, Table, text
from sqlalchemy import inspect as inspect_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

from src import config
from src.config import DEFAULT_APP_DATABASE_URL, load_persistence_settings
from src.infrastructure.persistence.database import create_app_engine, create_persistence_runtime
from src.project_paths import BACKEND_ROOT, CONFIG_DIR, DATA_DIR


def test_persistence_settings_环境变量覆盖本地配置(monkeypatch: pytest.MonkeyPatch) -> None:
    """应用数据库 URL 使用独立环境变量，优先级高于本地配置。"""
    monkeypatch.setattr(
        config,
        "_load_yaml_config",
        lambda: {"persistence": {"database_url": "sqlite:///from-local.sqlite3"}},
    )
    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", "sqlite:///from-env.sqlite3")

    settings = load_persistence_settings()

    assert settings.database_url == "sqlite:///from-env.sqlite3"


def test_persistence_settings_默认根数据目录_sqlite(monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置 URL 时开发默认值固定在根 data 目录。"""
    monkeypatch.setattr(config, "_load_yaml_config", dict)
    monkeypatch.delenv("OPERMIND_APP_DATABASE_URL", raising=False)

    settings = load_persistence_settings()

    assert settings.database_url == DEFAULT_APP_DATABASE_URL
    assert (DATA_DIR / "opermind.sqlite3").as_posix() in settings.database_url

def test_persistence_settings_空配置段回退默认值(monkeypatch: pytest.MonkeyPatch) -> None:
    """注释型 YAML 解析出的空 persistence 段也必须安全回退。"""
    monkeypatch.setattr(config, "_load_yaml_config", lambda: {"persistence": None})
    monkeypatch.delenv("OPERMIND_APP_DATABASE_URL", raising=False)

    assert load_persistence_settings().database_url == DEFAULT_APP_DATABASE_URL

def test_persistence_settings_环境变量覆盖空配置段(monkeypatch: pytest.MonkeyPatch) -> None:
    """空 persistence 段不能阻止独立应用数据库环境变量覆盖。"""
    monkeypatch.setattr(config, "_load_yaml_config", lambda: {"persistence": None})
    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", "sqlite:///from-env.sqlite3")

    assert load_persistence_settings().database_url == "sqlite:///from-env.sqlite3"

def test_persistence_配置模板显式声明空映射() -> None:
    """模板必须可解析，并让未配置的 persistence 保持空映射。"""
    template = yaml.safe_load((CONFIG_DIR / "config.example.yaml").read_text(encoding="utf-8"))

    assert template["persistence"] == {}


def test_sqlite_runtime_启用外键并支持回滚(tmp_path: Path) -> None:
    """SQLite 运行时必须开启外键，Session rollback 不提交未完成事务。"""
    database_url = f"sqlite:///{(tmp_path / 'runtime.sqlite3').as_posix()}"
    runtime = create_persistence_runtime(database_url)
    try:
        with runtime.engine.begin() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
            connection.execute(text("CREATE TABLE parent (id INTEGER PRIMARY KEY)"))
            connection.execute(
                text(
                    "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER NOT NULL, "
                    "FOREIGN KEY(parent_id) REFERENCES parent(id))"
                )
            )

        session = runtime.session_factory()
        try:
            session.execute(text("INSERT INTO parent (id) VALUES (1)"))
            session.rollback()
        finally:
            session.close()

        with runtime.engine.connect() as connection:
            assert connection.execute(text("SELECT COUNT(*) FROM parent")).scalar_one() == 0

        session = runtime.session_factory()
        try:
            with pytest.raises(IntegrityError):
                session.execute(text("INSERT INTO child (id, parent_id) VALUES (1, 999)"))
                session.commit()
        finally:
            session.rollback()
            session.close()
    finally:
        runtime.engine.dispose()


def test_postgresql_runtime_可在不连接时构造() -> None:
    """PostgreSQL URL 只构造方言和连接池，不在基础测试中连接真实服务。"""
    engine = create_app_engine("postgresql+psycopg://opermind:password@localhost/opermind")
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()

def test_postgresql_runtime_拒绝未锁定默认驱动() -> None:
    """PostgreSQL URL 必须显式选择已锁定的 psycopg 驱动。"""
    with pytest.raises(ValueError, match=r"postgresql\+psycopg"):
        create_app_engine("postgresql://opermind:password@localhost/opermind")

def test_postgresql_方言可编译跨方言约束() -> None:
    """P2 可移植表约束必须能在 PostgreSQL 方言下编译。"""
    metadata = MetaData()
    probe = Table(
        "portable_probe",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer, nullable=False),
    )

    ddl = str(CreateTable(probe).compile(dialect=postgresql.dialect()))

    assert "CREATE TABLE portable_probe" in ddl
    assert "SERIAL" in ddl


def test_persistence_runtime_拒绝非目标数据库方言() -> None:
    """应用元数据基础设施不接受未来诊断数据源的 MySQL URL。"""
    with pytest.raises(ValueError, match="sqlite 或 postgresql"):
        create_app_engine("mysql+pymysql://readonly@localhost/diagnosis")


def test_alembic_upgrade_head_仅创建迁移版本元数据(tmp_path: Path) -> None:
    """P2/P4.2 migration 的 fresh-db 迁移创建预期业务表。"""
    database_path = tmp_path / "fresh.sqlite3"
    env = os.environ.copy()
    env.update(
        {
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
        }
    )
    command = [
        sys.executable,
        "-m",
        "alembic",
        "-c",
        str(BACKEND_ROOT / "alembic.ini"),
        "upgrade",
        "head",
    ]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    engine = create_app_engine(env["OPERMIND_APP_DATABASE_URL"])
    try:
        assert set(inspect_engine(engine).get_table_names()) == {
            "alembic_version",
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
            "service_monitor_thresholds",
            "model_providers",
            "model_provider_idempotency_keys",
            "service_registry",
            "app_settings",
            "model_usage_records",
        }
    finally:
        engine.dispose()
