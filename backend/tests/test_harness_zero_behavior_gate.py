"""P10 S3 zero-behavior baseline 的 pytest 机器门禁。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.support import harness_zero_behavior as gate

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = REPO_ROOT / gate.BASELINE_PATH


@pytest.fixture(scope="module")
def baseline() -> dict[str, Any]:
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _fresh_process_openapi_sha() -> str:
    """在干净解释器中计算 OpenAPI，隔离其他测试对已导入 app 的临时改装。"""

    environment = os.environ.copy()
    environment.update(
        {
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
            "PYTHONPATH": os.pathsep.join(
                [str(REPO_ROOT / "backend"), str(REPO_ROOT), environment.get("PYTHONPATH", "")]
            ),
        }
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "from tests.support.harness_zero_behavior import _openapi_sha; "
                "print(_openapi_sha(Path(__import__('sys').argv[1])))"
            ),
            str(REPO_ROOT),
        ],
        cwd=REPO_ROOT / "backend",
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise AssertionError("zero_behavior.openapi_subprocess：干净进程取样失败")
    return completed.stdout.strip()


def test_dependency_openapi_alembic与受保护生产面保持baseline(baseline: dict[str, Any]) -> None:
    assert gate._hash_files(REPO_ROOT, "HEAD", gate.DEPENDENCY_PATHS) == baseline[
        "dependency_git_blob_sha256"
    ]
    assert gate._hash_files(REPO_ROOT, "HEAD", gate.PROTECTED_FILES) == baseline[
        "protected_file_git_blob_sha256"
    ]
    assert {
        prefix: gate._aggregate_prefix(REPO_ROOT, "HEAD", prefix)
        for prefix in gate.PROTECTED_PREFIXES
    } == baseline["protected_tree_aggregate_sha256"]
    assert _fresh_process_openapi_sha() == baseline["openapi_normalized_sha256"]
    assert gate._alembic_heads(REPO_ROOT) == baseline["alembic_heads"]


def test_committed_staged_unstaged_untracked四集合精确受allowlist约束(
    baseline: dict[str, Any],
) -> None:
    base_sha = str(baseline["base_commit_sha"])
    inventory = gate._diff_inventory(REPO_ROOT, base_sha)
    closeout_inventory = {
        name: [path for path in paths if path != "docs/路线图.md"]
        for name, paths in inventory.items()
    }

    assert set(inventory) == {"committed", "staged", "unstaged", "untracked"}
    assert "docs/路线图.md" in gate._inventory_union(inventory)
    gate._assert_allowed_inventory(closeout_inventory, bootstrap=False)
    dirty = gate._inventory_union(inventory)
    assert not set(gate.PROTECTED_FILES) & dirty
    assert not any(path.startswith(gate.PROTECTED_PREFIXES) for path in dirty)

    negative_inventory = {name: list(paths) for name, paths in closeout_inventory.items()}
    negative_inventory["untracked"].append("backend/src/app.py")
    with pytest.raises(gate.GateError, match="四集合包含越界路径"):
        gate._assert_allowed_inventory(negative_inventory, bootstrap=False)


def test_baseline与generator提交后不可变(baseline: dict[str, Any]) -> None:
    baseline_raw = BASELINE_PATH.read_bytes()
    assert gate._verify_baseline_immutability(REPO_ROOT, baseline_raw) is True
    generator = baseline["generator"]
    assert isinstance(generator, dict)
    gate._verify_generator_hashes(REPO_ROOT, generator, baseline_committed=True)


def test_contract生产import_graph保持隔离且负向样例会失败() -> None:
    gate._verify_import_boundaries(REPO_ROOT)

    violations = gate._inspect_production_module(
        "backend/src/application/services.py",
        "negative_sample",
        b"from src.application.runtime_contracts import RuntimeAdapterContract\n",
    )
    assert any("src.application.runtime_contracts" in item for item in violations)


def test_skip_xfail_inventory未增长且候选文件为零(baseline: dict[str, Any]) -> None:
    assert gate._skip_inventory(REPO_ROOT, "HEAD") == baseline["skip_xfail_inventory"]
    assert gate._candidate_skip_inventory(REPO_ROOT) == []


def test_capability_profile历史不可覆盖且版本连续(baseline: dict[str, Any]) -> None:
    expected_history = baseline["capability_profile_history"]
    assert isinstance(expected_history, dict)
    gate._verify_profile_ratchet(REPO_ROOT, str(baseline["base_commit_sha"]), expected_history)


def test_正式路线图P10范围与PRD一致() -> None:
    roadmap = (REPO_ROOT / "docs" / "路线图.md").read_text(encoding="utf-8")
    assert "P10 已完成：Agent Harness 契约内核与回归基线" in roadmap
    assert "Harness Contract Kernel" in roadmap
    assert "Adapter Contract Test Harness" in roadmap
    assert "Regression Baseline" in roadmap
    assert "P9 产出的 A–E 只表示依赖顺序，不是已批准阶段或 Workpack" in roadmap
    assert "P10 只包含已确认的三个零行为变化切片，不自动承诺 A 的其余内容或 B–E" in roadmap
