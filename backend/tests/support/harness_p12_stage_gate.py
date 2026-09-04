"""P12 exact-path、历史门与只读能力边界验证。"""

from __future__ import annotations

import ast
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.support.harness_p11_stage_gate import verify as verify_p11

MANIFEST_PATH: Final = "backend/tests/fixtures/harness/p12_stage_manifest.v1.json"
BASE_SHA: Final = "73292fbf4bf1a772849c94f54fe0e0b3e2108c08"


class StageGateError(RuntimeError):
    """P12 阶段边界被突破。"""


def load_manifest(root: Path) -> dict[str, Any]:
    try:
        payload = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StageGateError("P12 manifest 无法读取") from error
    if payload.get("schema_version") != 1 or payload.get("phase") != "P12" or payload.get("issue") != 124:
        raise StageGateError("P12 manifest 身份无效")
    if payload.get("base_commit_sha") != BASE_SHA:
        raise StageGateError("P12 base SHA 漂移")
    allowed = payload.get("allowed_paths")
    if not isinstance(allowed, list) or len(allowed) != len(set(allowed)):
        raise StageGateError("P12 exact path 无效")
    if any(not isinstance(path, str) or "*" in path or path.endswith("/") for path in allowed):
        raise StageGateError("P12 禁止通配或目录 allowlist")
    return payload


def _git(root: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args],  # noqa: S607 - repository-local read-only inventory
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise StageGateError("P12 git inventory 无法读取")
    return [item.replace("\\", "/") for item in result.stdout.splitlines() if item]


def current_inventory(root: Path) -> dict[str, list[str]]:
    return {
        "committed": _git(root, "diff", "--name-only", f"{BASE_SHA}...HEAD"),
        "staged": _git(root, "diff", "--cached", "--name-only"),
        "unstaged": _git(root, "diff", "--name-only"),
        "untracked": _git(root, "ls-files", "--others", "--exclude-standard"),
    }


def assert_allowed_inventory(inventory: Mapping[str, list[str]], allowed: set[str]) -> None:
    if set(inventory) != {"committed", "staged", "unstaged", "untracked"}:
        raise StageGateError("P12 四集合类别不完整")
    changed = {path for values in inventory.values() for path in values}
    rejected = sorted(changed - allowed)
    if rejected:
        raise StageGateError(f"P12 四集合包含越界路径：{', '.join(rejected)}")


def assert_no_skip_xfail(root: Path, paths: list[str]) -> None:
    for relative in paths:
        if not relative.startswith("backend/tests/") or not relative.endswith(".py"):
            continue
        source = (root / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"skip", "skipif", "xfail", "xpass"}:
                raise StageGateError(f"P12 禁止新增 skip/xfail/xpass：{relative}")


def assert_readonly_source_boundaries(
    *,
    preflight_source: str,
    redis_source: str,
    mysql_source: str,
) -> None:
    """以可变异输入证明 preflight 与两类 Connector 无通用执行逃生口。"""
    for forbidden in (
        "import sqlalchemy",
        "from sqlalchemy",
        "import redis",
        "from redis",
        "import pymysql",
        "import psycopg",
        "import socket",
        "import httpx",
        "import requests",
    ):
        if forbidden in preflight_source.lower():
            raise StageGateError("P12 preflight 不得装载外部访问能力")
    for forbidden in (
        "execute_command(",
        "client.keys(",
        "client.scan(",
        "client.get(",
        "client.set(",
        "client.delete(",
        "client.flush",
        "client.eval(",
    ):
        if forbidden in redis_source.lower():
            raise StageGateError("P12 Redis Connector 出现越界命令")
    mysql_lower = mysql_source.lower()
    for forbidden in (
        "processlist",
        "select *",
        " insert ",
        " update ",
        " delete ",
        " alter ",
        " drop ",
        " truncate ",
        " execute(",
    ):
        if forbidden in mysql_lower:
            raise StageGateError("P12 MySQL Connector 出现越界 SQL")
    if mysql_source.count("connection.execute(text(") != 2:
        raise StageGateError("P12 MySQL Connector 必须只执行两个固定语句")
    for required in (
        '"SHOW GLOBAL STATUS WHERE Variable_name IN "',
        '"SHOW GLOBAL VARIABLES WHERE Variable_name = \'max_connections\'"',
        "connection.execute(text(_STATUS_SQL))",
        "connection.execute(text(_VARIABLE_SQL))",
    ):
        if required not in mysql_source:
            raise StageGateError("P12 MySQL 固定指标 SQL 漂移")


def assert_boundaries(root: Path, manifest: Mapping[str, Any]) -> None:
    if (root / "backend/tests/conftest.py") in [root / path for path in manifest["allowed_paths"]]:
        raise StageGateError("P12 不得修改 pytest 外联阻断器")
    requirements = (root / "backend/requirements.txt").read_text(encoding="utf-8")
    if requirements.count("PyMySQL==1.2.0") != 1:
        raise StageGateError("P12 MySQL 驱动依赖必须唯一锁定")
    domain_services = (root / "backend/src/domain/services.py").read_text(encoding="utf-8")
    if 'frozenset({"postgres", "redis", "mysql"})' not in domain_services:
        raise StageGateError("P12 服务类型集合必须精确为三类")
    migration = (root / "backend/migrations/versions/20260904_15_p12_mysql_service_kind.py").read_text(
        encoding="utf-8"
    )
    for required in (
        'revision = "20260904_15_p12_mysql_kind"',
        'down_revision = "20260815_14_merge_p8_heads"',
        "batch_alter_table",
        "WHERE kind = 'mysql'",
    ):
        if required not in migration:
            raise StageGateError("P12 migration 边界不完整")
    config = Config(str(root / "backend/alembic.ini"))
    if ScriptDirectory.from_config(config).get_heads() != ["20260904_15_p12_mysql_kind"]:
        raise StageGateError("P12 Alembic 必须保持单一 head")
    preflight = (root / "backend/scripts/check_p12_real_readonly_preflight.py").read_text(encoding="utf-8")
    health_tools = (root / "backend/src/tools/service_health_tools.py").read_text(encoding="utf-8")
    if '"additionalProperties": False' not in health_tools:
        raise StageGateError("P12 健康 Tool 必须拒绝额外参数")
    redis_source = (root / "backend/src/infrastructure/services/redis_connector.py").read_text(encoding="utf-8")
    mysql_source = (root / "backend/src/infrastructure/services/mysql_connector.py").read_text(encoding="utf-8")
    assert_readonly_source_boundaries(
        preflight_source=preflight,
        redis_source=redis_source,
        mysql_source=mysql_source,
    )


def verify(root: Path) -> dict[str, list[str]]:
    manifest = load_manifest(root)
    allowed = set(manifest["allowed_paths"])
    inventory = current_inventory(root)
    assert_allowed_inventory(inventory, allowed)
    assert_no_skip_xfail(root, manifest["allowed_paths"])
    assert_boundaries(root, manifest)
    verify_p11(root)
    return inventory
