"""P12 独立 exact-path 与负向边界门。"""

from pathlib import Path

import pytest

from tests.support.harness_p12_stage_gate import (
    StageGateError,
    assert_allowed_inventory,
    assert_boundaries,
    assert_no_skip_xfail,
    assert_readonly_source_boundaries,
    load_manifest,
    verify,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_p12_stage_gate_verifies_current_tree() -> None:
    inventory = verify(REPO_ROOT)
    assert set(inventory) == {"committed", "staged", "unstaged", "untracked"}


def test_manifest_is_exact_without_globs() -> None:
    manifest = load_manifest(REPO_ROOT)
    assert all("*" not in path and not path.endswith("/") for path in manifest["allowed_paths"])


def test_any_out_of_scope_path_fails() -> None:
    inventory = {"committed": [], "staged": [], "unstaged": [], "untracked": ["backend/src/app.py"]}
    with pytest.raises(StageGateError, match="越界路径"):
        assert_allowed_inventory(inventory, {"backend/**"})


def test_skip_or_xfail_in_p12_test_fails(tmp_path: Path) -> None:
    relative = "backend/tests/test_bad.py"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text("import pytest\npytest.skip('bad')\n", encoding="utf-8")
    with pytest.raises(StageGateError, match="skip/xfail"):
        assert_no_skip_xfail(tmp_path, [relative])


def test_missing_mysql_allowlist_fails(tmp_path: Path) -> None:
    manifest = load_manifest(REPO_ROOT)
    for relative in (
        "backend/requirements.txt",
        "backend/src/domain/services.py",
        "backend/migrations/versions/20260904_15_p12_mysql_service_kind.py",
        "backend/alembic.ini",
        "backend/migrations",
        "backend/scripts/check_p12_real_readonly_preflight.py",
        "backend/src/tools/service_health_tools.py",
        "backend/src/infrastructure/services/redis_connector.py",
        "backend/src/infrastructure/services/mysql_connector.py",
    ):
        source = REPO_ROOT / relative
        target = tmp_path / relative
        if source.is_dir():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    domain_services = tmp_path / "backend/src/domain/services.py"
    domain_services.write_text(
        domain_services.read_text(encoding="utf-8").replace(
            'frozenset({"postgres", "redis", "mysql"})', 'frozenset({"postgres", "redis"})'
        ),
        encoding="utf-8",
    )
    with pytest.raises(StageGateError, match="服务类型集合"):
        assert_boundaries(tmp_path, manifest)


@pytest.mark.parametrize(
    "path",
    [
        "backend/migrations/versions/20260904_16_second_p12.py",
        "backend/src/api/v1/p12_public_api.py",
        "backend/src/infrastructure/services/mongodb_connector.py",
    ],
)
def test_scope_expansion_path_fails(path: str) -> None:
    with pytest.raises(StageGateError, match="越界路径"):
        assert_allowed_inventory(
            {"committed": [], "staged": [], "unstaged": [], "untracked": [path]},
            set(load_manifest(REPO_ROOT)["allowed_paths"]),
        )


@pytest.mark.parametrize(
    ("target", "mutation", "message"),
    [
        ("preflight", "\nimport redis\n", "preflight"),
        ("redis", "\nclient.execute_command('GET', 'key')\n", "Redis"),
        ("mysql", "\nconnection.execute(text('DELETE FROM business'))\n", "MySQL"),
    ],
)
def test_readonly_source_mutation_fails(target: str, mutation: str, message: str) -> None:
    sources = {
        "preflight_source": (REPO_ROOT / "backend/scripts/check_p12_real_readonly_preflight.py").read_text(
            encoding="utf-8"
        ),
        "redis_source": (REPO_ROOT / "backend/src/infrastructure/services/redis_connector.py").read_text(
            encoding="utf-8"
        ),
        "mysql_source": (REPO_ROOT / "backend/src/infrastructure/services/mysql_connector.py").read_text(
            encoding="utf-8"
        ),
    }
    sources[f"{target}_source"] += mutation
    with pytest.raises(StageGateError, match=message):
        assert_readonly_source_boundaries(**sources)
