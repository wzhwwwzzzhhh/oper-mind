"""P11 独立阶段门：精确变更面、P10 历史资产与安全边界。"""

from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from tests.support import harness_zero_behavior as p10_gate

MANIFEST_PATH: Final = "backend/tests/fixtures/harness/p11_stage_manifest.v1.json"
P10_BASELINE_PATH: Final = "backend/tests/fixtures/harness/zero_behavior_baseline.v1.json"
P10_GENERATOR_PATH: Final = "backend/tests/support/harness_zero_behavior.py"
P10_PROFILE_V1_PATH: Final = "backend/tests/fixtures/harness/current_capability_profile.v1.json"
P11_BASE_SHA: Final = "602323899595e2db34876d6cfc2f47e38ae74096"
P11_DELIVERY_SHA: Final = "990368fcda0f8673ed7e6c8963108e7746c1f8d4"
P10_DELIVERY_SHA: Final = "4d17f6f65f616774b3b616faaed03348dd5a1c08"
P11_OPENAPI_SHA256: Final = "a47be238cb5e3652b382a73a6b48d99af23a26608ec7fcf07b02556bae7b15a3"
P11_ALEMBIC_HEADS: Final = ["20260815_14_merge_p8_heads"]
ACTIVE_WORKPACK_PATHS: Final = frozenset(
    {
        "docs/workpack/P11-harness-real-runtime-safety-gate/evidence.md",
        "docs/workpack/P11-harness-real-runtime-safety-gate/plan.md",
        "docs/workpack/P11-harness-real-runtime-safety-gate/review.md",
    }
)
ARCHIVED_WORKPACK_PATHS: Final = frozenset(
    {
        "docs/workpack/归档/P11-harness-real-runtime-safety-gate/evidence.md",
        "docs/workpack/归档/P11-harness-real-runtime-safety-gate/plan.md",
        "docs/workpack/归档/P11-harness-real-runtime-safety-gate/review.md",
    }
)

ALLOWED_PATHS: Final = frozenset(
    {
        "backend/scripts/check_p11_real_resource_preflight.py",
        "backend/src/application/runtime_safety.py",
        "backend/src/application/services.py",
        "backend/src/core/tool_gateway.py",
        "backend/src/infrastructure/services/postgres_connector.py",
        "backend/tests/conftest.py",
        "backend/tests/fixtures/harness/current_capability_profile.v2.json",
        MANIFEST_PATH,
        "backend/tests/support/harness_p11_contracts.py",
        "backend/tests/support/harness_p11_stage_gate.py",
        "backend/tests/test_harness_p11_runtime_safety.py",
        "backend/tests/test_harness_p11_stage_gate.py",
        "backend/tests/test_harness_p11_tool_connector_safety.py",
        "backend/tests/test_harness_zero_behavior_gate.py",
        "docs/design/agent-runtime/P11AgentHarness真实运行安全门实施Design.md",
        "docs/workpack/P11-harness-real-runtime-safety-gate/evidence.md",
        "docs/workpack/P11-harness-real-runtime-safety-gate/plan.md",
        "docs/workpack/P11-harness-real-runtime-safety-gate/review.md",
        "docs/workpack/README.md",
        "docs/workpack/归档/P11-harness-real-runtime-safety-gate/evidence.md",
        "docs/workpack/归档/P11-harness-real-runtime-safety-gate/plan.md",
        "docs/workpack/归档/P11-harness-real-runtime-safety-gate/review.md",
    }
)
P11_TEST_PATHS: Final = (
    "backend/tests/support/harness_p11_contracts.py",
    "backend/tests/support/harness_p11_stage_gate.py",
    "backend/tests/test_harness_p11_runtime_safety.py",
    "backend/tests/test_harness_p11_stage_gate.py",
    "backend/tests/test_harness_p11_tool_connector_safety.py",
)
REQUIRED_NEGATIVE_PROBES: Final = {
    "backend/tests/test_harness_zero_behavior_gate.py": (
        "test_P10交付树的依赖OpenAPI迁移与受保护生产面保持baseline",
        "test_P10历史交付diff精确受原allowlist约束且负向样例仍失败",
        "test_baseline与generator提交后不可变",
        "test_P10历史contract生产import_graph保持隔离且负向样例会失败",
        "test_skip_xfail_inventory未增长且候选文件为零",
        "test_capability_profile历史不可覆盖且版本连续",
        "test_正式路线图P10范围与PRD一致",
    ),
    "backend/tests/test_harness_p11_runtime_safety.py": (
        "test_零多终止终止后输出和非法对象失败关闭",
        "test_终止候选后再抛typed_error按多终止违例关闭",
        "test_各阶段意外异常统一为安全typed_failure",
        "test_只改capability声明不能替代行为证明",
    ),
    "backend/tests/test_harness_p11_tool_connector_safety.py": (
        "test_运行中Tool超时关闭接纳并隔离迟到内容",
        "test_排队future超时取消后永不补执行",
        "test_Tool自身TimeoutError不等于Gateway等待超时",
        "test_shutdown取消排队future不得误报为已完成",
        "test_PostgreSQL非法查询和标识符在连接前拒绝",
        "test_Redis限时只读命令与失败收敛",
        "test_普通测试环境默认离线且低层入口失败关闭",
        "test_带真实配置哨兵的子进程在collection前被净化",
        "test_真实测试软件门缺任一条件均在访问前失败关闭",
    ),
    "backend/tests/test_harness_p11_stage_gate.py": (
        "test_P11历史交付diff不吸收后续阶段文件",
        "test_四集合任一越界文件都会失败",
        "test_目录通配白名单不能掩盖越界文件",
        "test_P11测试support出现skip会失败",
        "test_删除必备负向探针会失败",
        "test_删除必备负向断言会失败",
        "test_离线门DNS入口与生命周期约束不可削弱",
    ),
}
REQUIRED_PROBE_SOURCE_SHA256: Final = {
    (
        "backend/tests/test_harness_zero_behavior_gate.py",
        "test_P10历史交付diff精确受原allowlist约束且负向样例仍失败",
    ): "c478a67da870099b1cef80012f1c123c7cf91d057a8fe36b872eb4098060514a",
    (
        "backend/tests/test_harness_zero_behavior_gate.py",
        "test_P10历史contract生产import_graph保持隔离且负向样例会失败",
    ): "e636392da13712a216f28963bc7ae74f2724fbf058a26fe782b2a1c6a681b0ce",
}


class StageGateError(RuntimeError):
    """P11 阶段边界被突破。"""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def function_source_sha256(source: str, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """对函数源码做跨 Python AST 版本稳定的精确指纹。"""

    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines(keepends=True)
    if node.end_lineno is None:
        raise StageGateError("P11 无法确定必备负向探针源码边界")
    segment = "".join(lines[node.lineno - 1 : node.end_lineno]).rstrip("\n") + "\n"
    return _sha256(segment.encode("utf-8"))


def load_manifest(root: Path) -> dict[str, Any]:
    """加载并校验 P11 manifest 的不可扩张骨架。"""

    try:
        payload = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StageGateError("P11 manifest 无法读取") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise StageGateError("P11 manifest schema 无效")
    if payload.get("phase") != "P11" or payload.get("issue") != 121:
        raise StageGateError("P11 manifest 阶段或 issue 无效")
    allowed = payload.get("allowed_paths")
    if not isinstance(allowed, list) or set(allowed) != ALLOWED_PATHS or len(allowed) != len(ALLOWED_PATHS):
        raise StageGateError("P11 manifest 必须使用 Design 确认的 exact path 集合")
    if any("*" in path or path.endswith("/") for path in allowed):
        raise StageGateError("P11 manifest 禁止通配或目录级 allowlist")
    active = payload.get("active_workpack_paths")
    archived = payload.get("archived_workpack_paths")
    if (
        not isinstance(active, list)
        or set(active) != ACTIVE_WORKPACK_PATHS
        or len(active) != len(ACTIVE_WORKPACK_PATHS)
        or not isinstance(archived, list)
        or set(archived) != ARCHIVED_WORKPACK_PATHS
        or len(archived) != len(ARCHIVED_WORKPACK_PATHS)
        or ACTIVE_WORKPACK_PATHS & ARCHIVED_WORKPACK_PATHS
    ):
        raise StageGateError("P11 manifest Workpack 路径必须是固定非空 3+3 互斥集合")
    return payload


def assert_allowed_inventory(
    inventory: Mapping[str, list[str]],
    allowed_paths: set[str] | frozenset[str] = ALLOWED_PATHS,
) -> None:
    """四集合任一越界路径都失败。"""

    if set(inventory) != {"committed", "staged", "unstaged", "untracked"}:
        raise StageGateError("P11 四集合类别不完整")
    changed = {path.replace("\\", "/") for paths in inventory.values() for path in paths}
    rejected = sorted(changed - set(allowed_paths))
    if rejected:
        raise StageGateError(f"P11 四集合包含越界路径：{', '.join(rejected)}")


def historical_inventory(root: Path, base_sha: str, delivery_sha: str) -> dict[str, list[str]]:
    """只重放 P11 已交付提交，不把后续阶段的 HEAD / 工作区变化吸入历史门。"""

    try:
        p10_gate._run_git(root, "merge-base", "--is-ancestor", base_sha, delivery_sha)
        p10_gate._run_git(root, "merge-base", "--is-ancestor", delivery_sha, "HEAD")
        raw_diff = p10_gate._run_git(
            root,
            "diff",
            "--no-renames",
            "--name-only",
            "-z",
            f"{base_sha}...{delivery_sha}",
        )
        if not isinstance(raw_diff, bytes):
            raise StageGateError("P11 历史交付 diff 类型无效")
        committed = p10_gate._nul_paths(raw_diff)
    except p10_gate.GateError as error:
        raise StageGateError("P11 历史交付提交不可验证") from error
    return {
        "committed": committed,
        "staged": [],
        "unstaged": [],
        "untracked": [],
    }


def assert_workpack_exclusive(root: Path, manifest: Mapping[str, Any]) -> None:
    """active 与 archive 只能存在一份完整工作包。"""

    active = manifest.get("active_workpack_paths")
    archived = manifest.get("archived_workpack_paths")
    if not isinstance(active, list) or set(active) != ACTIVE_WORKPACK_PATHS:
        raise StageGateError("P11 manifest Workpack 路径必须是固定非空 3+3 互斥集合")
    if not isinstance(archived, list) or set(archived) != ARCHIVED_WORKPACK_PATHS:
        raise StageGateError("P11 manifest Workpack 路径必须是固定非空 3+3 互斥集合")
    active_present = {path for path in ACTIVE_WORKPACK_PATHS if (root / path).is_file()}
    archived_present = {path for path in ARCHIVED_WORKPACK_PATHS if (root / path).is_file()}
    if not (
        (active_present == ACTIVE_WORKPACK_PATHS and not archived_present)
        or (archived_present == ARCHIVED_WORKPACK_PATHS and not active_present)
    ):
        raise StageGateError("P11 active/归档 Workpack 必须完整、唯一且互斥")


def assert_no_skip_xfail(root: Path, paths: tuple[str, ...] = P11_TEST_PATHS) -> None:
    """AST 检查新增 P11 测试/support 没有跳过入口。"""

    for relative in paths:
        source = (root / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        visitor = p10_gate._SkipInventoryVisitor(relative)
        visitor.visit(tree)
        if visitor.entries:
            raise StageGateError(f"P11 新增测试/support 禁止 skip/xfail：{relative}")


def assert_required_probe_inventory(
    root: Path,
    required: Mapping[str, tuple[str, ...]] = REQUIRED_NEGATIVE_PROBES,
    required_fingerprints: Mapping[tuple[str, str], str] = REQUIRED_PROBE_SOURCE_SHA256,
) -> None:
    """必备负向行为探针不得被删除或藏入非顶层作用域。"""

    for relative, expected_names in required.items():
        source = (root / relative).read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative)
        definitions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        missing = sorted(set(expected_names) - set(definitions))
        if missing:
            raise StageGateError(f"P11 缺少必备负向探针：{relative}:{', '.join(missing)}")
        for name in expected_names:
            nodes = tuple(ast.walk(definitions[name]))
            has_assertion = any(isinstance(node, ast.Assert) for node in nodes)
            has_expected_failure = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "raises"
                for node in nodes
            )
            if not has_assertion and not has_expected_failure:
                raise StageGateError(f"P11 必备负向探针缺少断言：{relative}:{name}")
            expected_sha = required_fingerprints.get((relative, name))
            if expected_sha is not None:
                actual_sha = function_source_sha256(source, definitions[name])
                if actual_sha != expected_sha:
                    raise StageGateError(f"P11 必备负向探针内容漂移：{relative}:{name}")


def assert_offline_blocker_source(source: str) -> None:
    """默认离线门必须覆盖常见 DNS 入口并保持到进程退出。"""

    required = (
        'patcher.setattr(socket, "getaddrinfo"',
        'patcher.setattr(socket, "gethostbyname"',
        'patcher.setattr(socket, "gethostbyname_ex"',
        'patcher.setattr(socket, "gethostbyaddr"',
        'patcher.setattr(socket, "getnameinfo"',
        "atexit.register(_OFFLINE_TEMP_DIRECTORY.cleanup)",
    )
    if any(item not in source for item in required):
        raise StageGateError("P11 离线门缺少 DNS 入口或进程退出清理")
    if "_COLLECTION_TIME_PATCHER.undo()" in source:
        raise StageGateError("P11 离线门不得在 pytest 进程退出前撤销")


def assert_p10_assets(root: Path, manifest: Mapping[str, Any]) -> None:
    """P10 baseline、generator 和 v1 profile 必须保持历史 Git blob。"""

    assets = manifest.get("p10_assets")
    if not isinstance(assets, dict):
        raise StageGateError("P11 manifest 缺少 P10 资产声明")
    checks = {
        "baseline_git_blob_sha256": p10_gate._git_blob_sha(root, "HEAD", P10_BASELINE_PATH),
        "generator_git_blob_sha256": p10_gate._git_blob_sha(root, "HEAD", P10_GENERATOR_PATH),
        "profile_v1_git_blob_sha256": p10_gate._git_blob_sha(root, "HEAD", P10_PROFILE_V1_PATH),
    }
    if checks != assets:
        raise StageGateError("P10 baseline/generator/v1 profile 历史资产发生变化")


def assert_production_boundaries(
    root: Path,
    manifest: Mapping[str, Any],
    delivery_sha: str,
) -> None:
    """在 P11 交付树验证阶段边界，并在当前树保留安全不变量。"""

    baseline = json.loads((root / P10_BASELINE_PATH).read_text(encoding="utf-8"))
    if p10_gate._hash_files(root, delivery_sha, p10_gate.DEPENDENCY_PATHS) != baseline[
        "dependency_git_blob_sha256"
    ]:
        raise StageGateError("P11 不得修改依赖清单")
    aggregates = {
        prefix: p10_gate._aggregate_prefix(root, delivery_sha, prefix)
        for prefix in p10_gate.PROTECTED_PREFIXES
    }
    if aggregates != baseline["protected_tree_aggregate_sha256"]:
        raise StageGateError("P11 不得修改 API、迁移或前端")
    if manifest.get("openapi_normalized_sha256") != P11_OPENAPI_SHA256:
        raise StageGateError("P11 交付 OpenAPI 证据漂移")
    if manifest.get("alembic_heads") != P11_ALEMBIC_HEADS:
        raise StageGateError("P11 交付 Alembic heads 证据漂移")

    assert_offline_blocker_source((root / "backend/tests/conftest.py").read_text(encoding="utf-8"))

    runtime_safety = (root / "backend/src/application/runtime_safety.py").read_text(encoding="utf-8")
    for forbidden in ("src.infrastructure", "src.core", "src.api", "src.agents", "sqlalchemy"):
        if forbidden in runtime_safety:
            raise StageGateError("Runtime guard 不得拥有业务 writer 或框架执行能力")
    importers = []
    for path in (root / "backend/src").rglob("*.py"):
        if "src.application.runtime_safety" in path.read_text(encoding="utf-8"):
            importers.append(path.relative_to(root).as_posix())
    if importers != ["backend/src/application/services.py"]:
        raise StageGateError("Runtime guard 必须只有 RunApplicationService 单点接线")

    preflight = (root / "backend/scripts/check_p11_real_resource_preflight.py").read_text(encoding="utf-8")
    for forbidden in ("socket", "httpx", "requests", "sqlalchemy", "redis", "psycopg", "urllib"):
        if forbidden in preflight:
            raise StageGateError("P11 preflight 不得导入或调用外部访问客户端")
    gateway = (root / "backend/src/core/tool_gateway.py").read_text(encoding="utf-8")
    if "future.cancel()" not in gateway or "add_done_callback" in gateway or "已中止" in gateway:
        raise StageGateError("ToolGateway timeout 取消/迟到隔离语义不完整")


def verify(root: Path) -> dict[str, list[str]]:
    """重放 P11 历史交付门，并验证当前树仍保留的安全不变量。"""

    manifest = load_manifest(root)
    base_sha = manifest.get("base_commit_sha")
    if base_sha != P11_BASE_SHA:
        raise StageGateError("P11 最终 origin/main base SHA 漂移")
    delivery_sha = manifest.get("delivery_commit_sha")
    if delivery_sha != P11_DELIVERY_SHA:
        raise StageGateError("P11 delivery SHA 漂移")
    if manifest.get("p10_delivery_sha") != P10_DELIVERY_SHA:
        raise StageGateError("P10 delivery SHA 漂移")
    inventory = historical_inventory(root, str(base_sha), str(delivery_sha))
    assert_allowed_inventory(inventory)
    assert_workpack_exclusive(root, manifest)
    assert_no_skip_xfail(root)
    assert_required_probe_inventory(root)
    assert_p10_assets(root, manifest)
    assert_production_boundaries(root, manifest, str(delivery_sha))
    return inventory
