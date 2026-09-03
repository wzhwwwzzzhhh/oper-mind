"""P11 独立阶段变更声明与不可绕过负向门禁。"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

from tests.support.harness_p11_stage_gate import (
    ACTIVE_WORKPACK_PATHS,
    ALLOWED_PATHS,
    ARCHIVED_WORKPACK_PATHS,
    StageGateError,
    assert_allowed_inventory,
    assert_no_skip_xfail,
    assert_offline_blocker_source,
    assert_required_probe_inventory,
    assert_workpack_exclusive,
    load_manifest,
    verify,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_P11阶段门验证当前四集合与全部边界() -> None:
    inventory = verify(REPO_ROOT)

    assert set(inventory) == {"committed", "staged", "unstaged", "untracked"}
    changed = {path for paths in inventory.values() for path in paths}
    assert changed <= ALLOWED_PATHS
    assert "backend/tests/fixtures/harness/p11_stage_manifest.v1.json" in changed


def test_manifest必须与代码内exact_path集合完全一致() -> None:
    manifest = load_manifest(REPO_ROOT)

    assert set(manifest["allowed_paths"]) == ALLOWED_PATHS
    assert all("*" not in path and not path.endswith("/") for path in manifest["allowed_paths"])


def test_四集合任一越界文件都会失败() -> None:
    inventory = {
        "committed": [],
        "staged": [],
        "unstaged": [],
        "untracked": ["backend/src/app.py"],
    }

    with pytest.raises(StageGateError, match="四集合包含越界路径"):
        assert_allowed_inventory(inventory)


def test_目录通配白名单不能掩盖越界文件() -> None:
    inventory = {
        "committed": [],
        "staged": [],
        "unstaged": ["backend/src/api/v1/routes.py"],
        "untracked": [],
    }

    with pytest.raises(StageGateError, match="四集合包含越界路径"):
        assert_allowed_inventory(inventory, frozenset({"backend/**"}))


def test_active与归档Workpack双份会失败(tmp_path: Path) -> None:
    for relative in ACTIVE_WORKPACK_PATHS | ARCHIVED_WORKPACK_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test", encoding="utf-8")

    with pytest.raises(StageGateError, match="完整、唯一且互斥"):
        assert_workpack_exclusive(
            tmp_path,
            {
                "active_workpack_paths": sorted(ACTIVE_WORKPACK_PATHS),
                "archived_workpack_paths": sorted(ARCHIVED_WORKPACK_PATHS),
            },
        )


def test_Workpack路径数组清空或篡改会失败() -> None:
    for active, archived in (
        ([], []),
        (["docs/workpack/P11/plan.md"], sorted(ARCHIVED_WORKPACK_PATHS)),
    ):
        with pytest.raises(StageGateError, match=r"固定非空 3\+3"):
            assert_workpack_exclusive(
                REPO_ROOT,
                {
                    "active_workpack_paths": active,
                    "archived_workpack_paths": archived,
                },
            )


def test_P11测试support出现skip会失败(tmp_path: Path) -> None:
    relative = "tests/test_negative.py"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text("import pytest\npytest.skip('forbidden')\n", encoding="utf-8")

    with pytest.raises(StageGateError, match="禁止 skip/xfail"):
        assert_no_skip_xfail(tmp_path, (relative,))


def test_删除必备负向探针会失败(tmp_path: Path) -> None:
    relative = "tests/test_required_probes.py"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text("def test_retained():\n    pass\n", encoding="utf-8")

    with pytest.raises(StageGateError, match="缺少必备负向探针"):
        assert_required_probe_inventory(
            tmp_path,
            {relative: ("test_retained", "test_deleted")},
        )


def test_删除必备负向断言会失败(tmp_path: Path) -> None:
    relative = "tests/test_required_assertions.py"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    original = ast.parse(
        "def test_retained():\n"
        "    assert True\n"
        "    with pytest.raises(RuntimeError):\n"
        "        raise RuntimeError\n"
    ).body[0]
    assert isinstance(original, ast.FunctionDef)
    original_sha = hashlib.sha256(
        ast.dump(original, annotate_fields=True, include_attributes=False).encode("utf-8")
    ).hexdigest()
    path.write_text("def test_retained():\n    assert True\n", encoding="utf-8")

    with pytest.raises(StageGateError, match="内容漂移"):
        assert_required_probe_inventory(
            tmp_path,
            {relative: ("test_retained",)},
            {(relative, "test_retained"): original_sha},
        )


def test_离线门DNS入口与生命周期约束不可削弱() -> None:
    source = (REPO_ROOT / "backend/tests/conftest.py").read_text(encoding="utf-8")
    assert_offline_blocker_source(source)

    with pytest.raises(StageGateError, match="缺少 DNS 入口"):
        assert_offline_blocker_source(source.replace('patcher.setattr(socket, "gethostbyname"', "removed"))
    with pytest.raises(StageGateError, match="不得在 pytest 进程退出前撤销"):
        assert_offline_blocker_source(source + "\n_COLLECTION_TIME_PATCHER.undo()\n")


def test_受控生产与preflight文件不含凭据字面量() -> None:
    paths = (
        "backend/src/application/runtime_safety.py",
        "backend/src/application/services.py",
        "backend/src/infrastructure/services/postgres_connector.py",
        "backend/scripts/check_p11_real_resource_preflight.py",
    )
    credential_uri = re.compile(r"[a-z][a-z0-9+.-]*://[^\s/@:]+:[^@\s]+@", re.IGNORECASE)
    for relative in paths:
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        assert credential_uri.search(source) is None
        assert "sk-" not in source.lower()


def test_manifest序列化不包含通配或凭据() -> None:
    serialized = json.dumps(load_manifest(REPO_ROOT), ensure_ascii=False)

    assert "backend/**" not in serialized
    assert "frontend/**" not in serialized
    assert re.search(r"://[^\s/@:]+:[^@\s]+@", serialized) is None
