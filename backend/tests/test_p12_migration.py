"""P12 MySQL kind CHECK 的 upgrade/downgrade 数据安全证据。"""

import os
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
PREVIOUS_REVISION = "20260815_14_merge_p8_heads"


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


def _insert(database_path: Path, kind: str, instance_id: str) -> None:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            now = "2026-09-04T00:00:00+00:00"
            connection.exec_driver_sql(
                "INSERT INTO service_registry "
                "(id, instance_id, kind, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid4()), instance_id, kind, instance_id, now, now),
            )
    finally:
        engine.dispose()


def test_upgrade_accepts_mysql_and_safe_downgrade_preserves_existing_rows(tmp_path: Path) -> None:
    database_path = tmp_path / "p12-safe.sqlite3"
    assert _alembic(database_path, "upgrade", PREVIOUS_REVISION).returncode == 0
    _insert(database_path, "postgres", "pg.keep")
    _insert(database_path, "redis", "redis.keep")

    upgrade = _alembic(database_path, "upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT instance_id, kind FROM service_registry ORDER BY instance_id"
            ).all() == [("pg.keep", "postgres"), ("redis.keep", "redis")]
    finally:
        engine.dispose()
    downgrade = _alembic(database_path, "downgrade", PREVIOUS_REVISION)
    assert downgrade.returncode == 0, downgrade.stderr
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            rows = connection.exec_driver_sql(
                "SELECT instance_id, kind FROM service_registry ORDER BY instance_id"
            ).all()
            assert rows == [("pg.keep", "postgres"), ("redis.keep", "redis")]
    finally:
        engine.dispose()
    with pytest.raises(IntegrityError):
        _insert(database_path, "mysql", "mysql.rejected")


def test_downgrade_with_mysql_row_fails_without_data_loss(tmp_path: Path) -> None:
    database_path = tmp_path / "p12-refuse.sqlite3"
    assert _alembic(database_path, "upgrade", "head").returncode == 0
    _insert(database_path, "mysql", "mysql.keep")

    downgrade = _alembic(database_path, "downgrade", PREVIOUS_REVISION)
    assert downgrade.returncode != 0
    assert "拒绝不安全回滚" in downgrade.stderr
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT kind FROM service_registry WHERE instance_id = 'mysql.keep'"
            ).scalar() == "mysql"
        _insert(database_path, "mysql", "mysql.still-allowed")
        with engine.connect() as connection:
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM service_registry WHERE kind = 'mysql'"
            ).scalar() == 2
    finally:
        engine.dispose()


def test_alembic_has_one_head() -> None:
    config = Config(str(ALEMBIC_INI))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == ["20260904_15_p12_mysql_kind"]
    assert len(script.get_heads()[0]) <= 32


def test_non_sqlite_upgrade_only_replaces_named_check(monkeypatch) -> None:
    migration_path = BACKEND_ROOT / "migrations/versions/20260904_15_p12_mysql_service_kind.py"
    spec = spec_from_file_location("p12_mysql_kind_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    class _Bind:
        dialect = type("Dialect", (), {"name": "postgresql"})()

        def execute(self, _statement):
            return type("ScalarResult", (), {"scalar": lambda self: 0})()

    class _Op:
        def get_bind(self):
            return _Bind()

        def drop_constraint(self, *args, **kwargs):
            calls.append(("drop_constraint", args, kwargs))

        def create_check_constraint(self, *args, **kwargs):
            calls.append(("create_check_constraint", args, kwargs))

        def batch_alter_table(self, *_args, **_kwargs):
            raise AssertionError("非 SQLite 不得使用 batch alter")

    monkeypatch.setattr(module, "op", _Op())
    module.upgrade()

    assert calls == [
        (
            "drop_constraint",
            ("service_registry_kind_valid", "service_registry"),
            {"type_": "check"},
        ),
        (
            "create_check_constraint",
            (
                "service_registry_kind_valid",
                "service_registry",
                "kind IN ('postgres', 'redis', 'mysql')",
            ),
            {},
        ),
    ]
    calls.clear()
    module.downgrade()
    assert calls == [
        (
            "drop_constraint",
            ("service_registry_kind_valid", "service_registry"),
            {"type_": "check"},
        ),
        (
            "create_check_constraint",
            (
                "service_registry_kind_valid",
                "service_registry",
                "kind IN ('postgres', 'redis')",
            ),
            {},
        ),
    ]
