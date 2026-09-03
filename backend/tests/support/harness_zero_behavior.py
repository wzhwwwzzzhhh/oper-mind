"""P10 Harness 零行为基线的受控生成与持续校验工具。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tokenize
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final

SCHEMA_VERSION: Final = 1
GENERATOR_PATH: Final = "backend/tests/support/harness_zero_behavior.py"
BASELINE_PATH: Final = "backend/tests/fixtures/harness/zero_behavior_baseline.v1.json"

BOOTSTRAP_ALLOWED_PATHS: Final = frozenset(
    {
        GENERATOR_PATH,
        "docs/workpack/P10-harness-contract-kernel/plan.md",
        "docs/workpack/README.md",
    }
)

FINAL_ALLOWED_EXACT_PATHS: Final = frozenset(
    {
        "backend/src/domain/harness_contracts.py",
        "backend/src/application/runtime_contracts.py",
        "backend/tests/support/__init__.py",
        "backend/tests/support/harness_contracts.py",
        GENERATOR_PATH,
        "backend/tests/fixtures/harness/current_capability_profile.v1.json",
        BASELINE_PATH,
        "backend/tests/test_harness_contract_kernel.py",
        "backend/tests/test_harness_runtime_adapter_contract.py",
        "backend/tests/test_harness_regression_baseline.py",
        "backend/tests/test_harness_zero_behavior_gate.py",
        "docs/workpack/README.md",
        "docs/design/agent-runtime/P9HarnessContractKernel实施Design.md",
        "docs/prd/agent-runtime/P9-harness-contract-kernel.md",
        "docs/prd/agent-runtime/README.md",
        "docs/prd/README.md",
    }
)
FINAL_ALLOWED_PREFIXES: Final = (
    "docs/workpack/P10-harness-contract-kernel/",
    "docs/workpack/归档/P10-harness-contract-kernel/",
)

DEPENDENCY_PATHS: Final = (
    "backend/requirements.txt",
    "backend/pyproject.toml",
    "frontend/package.json",
    "frontend/package-lock.json",
)
PROTECTED_FILES: Final = (
    "backend/src/app.py",
    "backend/src/application/contracts.py",
    "backend/src/application/services.py",
    "backend/src/application/action_services.py",
    "backend/src/core/tool_gateway.py",
    "backend/src/infrastructure/diagnosis/coordinator_executor.py",
    "backend/src/api/v1/dependencies.py",
)
PROTECTED_PREFIXES: Final = (
    "backend/migrations/",
    "backend/src/api/v1/",
    "frontend/",
)
CONTRACT_MODULE_PATHS: Final = (
    "backend/src/domain/harness_contracts.py",
    "backend/src/application/runtime_contracts.py",
)
HARNESS_TEST_PATHS: Final = (
    "backend/tests/support/__init__.py",
    "backend/tests/support/harness_contracts.py",
    GENERATOR_PATH,
    "backend/tests/test_harness_contract_kernel.py",
    "backend/tests/test_harness_runtime_adapter_contract.py",
    "backend/tests/test_harness_regression_baseline.py",
    "backend/tests/test_harness_zero_behavior_gate.py",
)
PROFILE_PATTERN: Final = re.compile(
    r"^backend/tests/fixtures/harness/current_capability_profile\.v([1-9][0-9]*)\.json$"
)
FIRST_PROFILE_PATH: Final = "backend/tests/fixtures/harness/current_capability_profile.v1.json"
SKIP_CATEGORIES: Final = frozenset(
    {
        "pytest.skip",
        "pytest.xfail",
        "pytest.importorskip",
        "pytest.mark.skip",
        "pytest.mark.skipif",
        "pytest.mark.xfail",
        "unittest.skip",
        "unittest.skipIf",
        "unittest.skipUnless",
        "unittest.expectedFailure",
    }
)
FORBIDDEN_CONTRACT_IMPORT_ROOTS: Final = frozenset(
    {
        "src.core",
        "src.agents",
        "src.tools",
        "src.infrastructure",
        "src.api",
        "langgraph",
        "langchain",
        "langchain_core",
        "langchain_openai",
        "openai",
        "agents",
        "pydantic_ai",
        "autogen",
        "crewai",
    }
)
ALLOWED_CONTRACT_THIRD_PARTY_ROOTS: Final = frozenset({"pydantic"})
RUNTIME_ALLOWED_PROJECT_IMPORTS: Final = (
    "src.domain.harness_contracts",
    "src.application.contracts",
)


class GateError(RuntimeError):
    """表示零行为门禁拒绝继续。"""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_generator_bytes(raw: bytes) -> bytes:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise GateError("generator 必须是有效 UTF-8 文本") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _canonical_baseline_checkout_bytes(raw: bytes) -> bytes:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise GateError("zero-behavior baseline checkout 禁止 UTF-8 BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GateError("zero-behavior baseline checkout 必须是无 BOM UTF-8 文本") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _git_executable() -> str:
    executable = shutil.which("git")
    if executable is None:
        raise GateError("找不到 Git 可执行文件")
    return executable


def _run_git(root: Path, *args: str, text: bool = False) -> bytes | str:
    completed = subprocess.run(
        [_git_executable(), *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=text,
        encoding="utf-8" if text else None,
        errors="strict" if text else None,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip() if text else completed.stderr.decode("utf-8", "replace").strip()
        detail = stderr.splitlines()[-1] if stderr else "无错误摘要"
        raise GateError(f"Git plumbing 失败（git {' '.join(args)}）：{detail}")
    return completed.stdout


def _repo_root() -> Path:
    candidate = Path(__file__).resolve().parents[3]
    discovered = Path(str(_run_git(candidate, "rev-parse", "--show-toplevel", text=True)).strip()).resolve()
    if os.path.normcase(str(candidate)) != os.path.normcase(str(discovered)):
        raise GateError("generator 所在仓库根与 Git worktree 根不一致")
    return candidate


def _normalize_path(raw: str) -> str:
    normalized = PurePosixPath(raw.replace("\\", "/")).as_posix()
    if normalized.startswith(("/", "../")) or normalized == "..":
        raise GateError(f"Git 返回了越界路径：{raw!r}")
    return normalized


def _nul_paths(raw: bytes) -> list[str]:
    return sorted({_normalize_path(item.decode("utf-8")) for item in raw.split(b"\0") if item})


def _line_paths(raw: str) -> list[str]:
    return sorted({_normalize_path(item) for item in raw.splitlines() if item})


def _head_sha(root: Path) -> str:
    return str(_run_git(root, "rev-parse", "HEAD", text=True)).strip()


def _assert_full_commit(root: Path, supplied: str) -> str:
    actual = str(_run_git(root, "rev-parse", f"{supplied}^{{commit}}", text=True)).strip()
    if supplied.lower() != actual.lower():
        raise GateError("--base-sha 必须是完整 commit SHA，不能使用缩写或其他 ref")
    return actual


def _git_paths(root: Path, revision: str, prefix: str | None = None) -> list[str]:
    args = ["ls-tree", "-r", "-z", "--name-only", revision]
    if prefix is not None:
        args.extend(["--", prefix])
    return _nul_paths(bytes(_run_git(root, *args)))


def _git_blob(root: Path, revision: str, path: str) -> bytes:
    return bytes(_run_git(root, "show", f"{revision}:{path}"))


def _git_blob_sha(root: Path, revision: str, path: str) -> str:
    return _sha256(_git_blob(root, revision, path))


def _candidate_blobs(root: Path, path: str) -> list[tuple[str, bytes]]:
    blobs: list[tuple[str, bytes]] = []
    checkout = root / Path(*PurePosixPath(path).parts)
    if checkout.is_file():
        blobs.append(("checkout", checkout.read_bytes()))
    index_paths = set(_nul_paths(bytes(_run_git(root, "ls-files", "-z", "--", path))))
    if path in index_paths:
        blobs.append(("index", bytes(_run_git(root, "show", f":{path}"))))
    if path in set(_git_paths(root, "HEAD", path)):
        blobs.append(("HEAD", _git_blob(root, "HEAD", path)))
    return blobs


def _diff_inventory(root: Path, base_sha: str) -> dict[str, list[str]]:
    committed = _nul_paths(
        bytes(_run_git(root, "diff", "--no-renames", "--name-only", "-z", f"{base_sha}...HEAD"))
    )
    staged = _nul_paths(bytes(_run_git(root, "diff", "--no-renames", "--cached", "--name-only", "-z")))
    unstaged = _nul_paths(bytes(_run_git(root, "diff", "--no-renames", "--name-only", "-z")))
    untracked = _nul_paths(bytes(_run_git(root, "ls-files", "--others", "--exclude-standard", "-z")))
    return {
        "committed": committed,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
    }


def _inventory_union(inventory: dict[str, list[str]]) -> set[str]:
    return {path for paths in inventory.values() for path in paths}


def _is_final_allowed(path: str) -> bool:
    return path in FINAL_ALLOWED_EXACT_PATHS or any(path.startswith(prefix) for prefix in FINAL_ALLOWED_PREFIXES)


def _assert_allowed_inventory(inventory: dict[str, list[str]], *, bootstrap: bool) -> None:
    paths = _inventory_union(inventory)
    rejected = sorted(paths - BOOTSTRAP_ALLOWED_PATHS) if bootstrap else sorted(
        path for path in paths if not _is_final_allowed(path)
    )
    if rejected:
        mode = "bootstrap" if bootstrap else "P10"
        raise GateError(f"{mode} 四集合包含越界路径：{', '.join(rejected)}")
    if bootstrap and GENERATOR_PATH not in paths:
        raise GateError("bootstrap 四集合中必须包含经过 Review 的 generator")


def _hash_files(root: Path, revision: str, paths: Sequence[str]) -> dict[str, str]:
    tree = set(_git_paths(root, revision))
    missing = sorted(set(paths) - tree)
    if missing:
        raise GateError(f"受保护 tracked 文件缺失：{', '.join(missing)}")
    return {path: _git_blob_sha(root, revision, path) for path in paths}


def _aggregate_prefix(root: Path, revision: str, prefix: str) -> dict[str, Any]:
    paths = [path for path in _git_paths(root, revision, prefix) if path.startswith(prefix)]
    if not paths:
        raise GateError(f"受保护 tracked 目录为空或缺失：{prefix}")
    digest = hashlib.sha256()
    for path in paths:
        blob_digest = _git_blob_sha(root, revision, path)
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob_digest.encode("ascii"))
    return {"path_count": len(paths), "sha256": digest.hexdigest()}


def _openapi_sha(root: Path) -> str:
    backend = root / "backend"
    inserted_paths: list[str] = []
    for import_root in (str(root), str(backend)):
        if import_root not in sys.path:
            sys.path.insert(0, import_root)
            inserted_paths.append(import_root)
    previous_cwd = Path.cwd()
    try:
        os.chdir(backend)
        from src.app import app

        payload = app.openapi()
    finally:
        os.chdir(previous_cwd)
        for import_root in reversed(inserted_paths):
            sys.path.remove(import_root)
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256(normalized)


def _alembic_heads(root: Path) -> list[str]:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(root / "backend" / "alembic.ini"))
    return sorted(ScriptDirectory.from_config(config).get_heads())


def _decode_python(blob: bytes, path: str) -> str:
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(blob).readline)
        return blob.decode(encoding)
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise GateError(f"无法解码 Python 文件：{path}") from exc


def _qualified_name(node: ast.AST, aliases: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        base = _qualified_name(node.value, aliases)
        return f"{base}.{node.attr}" if base else None
    return None


class _RedactConstants(ast.NodeTransformer):
    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if node.value is None or isinstance(node.value, bool):
            return node
        label = f"<{type(node.value).__name__}>"
        return ast.copy_location(ast.Constant(value=label), node)


def _condition_details(node: ast.AST | None) -> tuple[str, str]:
    if node is None:
        return "unconditional", _sha256(b"unconditional")
    exact = ast.dump(node, annotate_fields=True, include_attributes=False).encode("utf-8")
    redacted = _RedactConstants().visit(ast.fix_missing_locations(ast.parse(ast.unparse(node), mode="eval")))
    summary = " ".join(ast.unparse(redacted.body).split())
    return summary[:240], _sha256(exact)


class _SkipInventoryVisitor(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self.aliases: dict[str, str] = {}
        self.scope: list[str] = []
        self.entries: dict[tuple[str, int, str, str], dict[str, Any]] = {}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            local = alias.asname or alias.name.split(".")[0]
            self.aliases[local] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is not None:
            for alias in node.names:
                self.aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        for decorator in node.decorator_list:
            self._scan_mark_tree(decorator, "decorator")
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        for decorator in node.decorator_list:
            self._scan_mark_tree(decorator, "decorator")
        self.generic_visit(node)
        self.scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if any(isinstance(target, ast.Name) and target.id == "pytestmark" for target in node.targets):
            self._scan_mark_tree(node.value, "module_mark")
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name) and node.target.id == "pytestmark" and node.value is not None:
            self._scan_mark_tree(node.value, "module_mark")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        qualified = _qualified_name(node.func, self.aliases)
        if qualified in SKIP_CATEGORIES:
            condition = self._condition_node(qualified, node)
            self._record(qualified, node, "call_or_marker", condition)
        if qualified == "pytest.param":
            for keyword in node.keywords:
                if keyword.arg == "marks":
                    self._scan_mark_tree(keyword.value, "param_mark")
        self.generic_visit(node)

    def _condition_node(self, category: str, call: ast.Call) -> ast.AST | None:
        if category in {
            "pytest.mark.skipif",
            "pytest.mark.xfail",
            "unittest.skipIf",
            "unittest.skipUnless",
        }:
            return call.args[0] if call.args else next(
                (item.value for item in call.keywords if item.arg == "condition"), None
            )
        if category in {"pytest.skip", "pytest.xfail", "pytest.importorskip", "unittest.skip"}:
            return call.args[0] if call.args else next(
                (item.value for item in call.keywords if item.arg in {"reason", "modname"}), None
            )
        return None

    def _scan_mark_tree(self, node: ast.AST, kind: str) -> None:
        qualified = _qualified_name(node.func, self.aliases) if isinstance(node, ast.Call) else _qualified_name(
            node, self.aliases
        )
        if qualified in SKIP_CATEGORIES:
            condition = self._condition_node(qualified, node) if isinstance(node, ast.Call) else None
            self._record(qualified, node, kind, condition)
            return
        for child in ast.iter_child_nodes(node):
            self._scan_mark_tree(child, kind)

    def _record(self, category: str, node: ast.AST, kind: str, condition: ast.AST | None) -> None:
        owner = "::".join(self.scope) if self.scope else "<module>"
        line = getattr(node, "lineno", 0)
        summary, condition_sha = _condition_details(condition)
        key = (category, line, owner, condition_sha)
        self.entries.setdefault(key, {
            "category": category,
            "condition_sha256": condition_sha,
            "condition_summary": summary,
            "entry_kind": kind,
            "file": self.path,
            "line": line,
            "owner": owner,
        })


def _skip_inventory(root: Path, revision: str) -> list[dict[str, Any]]:
    paths = [path for path in _git_paths(root, revision, "backend/tests") if path.endswith(".py")]
    entries: list[dict[str, Any]] = []
    for path in paths:
        source = _decode_python(_git_blob(root, revision, path), path)
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            raise GateError(f"无法解析 Python 测试文件：{path}:{exc.lineno or 0}") from exc
        visitor = _SkipInventoryVisitor(path)
        visitor.visit(tree)
        entries.extend(visitor.entries.values())
    return sorted(
        entries,
        key=lambda item: (
            str(item["file"]),
            int(item["line"]),
            str(item["category"]),
            str(item["entry_kind"]),
        ),
    )


def _module_name(path: Path, src_root: Path) -> str:
    relative = path.relative_to(src_root.parent).with_suffix("")
    return ".".join(relative.parts)


def _imports_from_tree(tree: ast.AST, module: str) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = module.split(".")[:-1]
                keep = len(package) - (node.level - 1)
                base_parts = package[: max(keep, 0)]
                if node.module:
                    base_parts.extend(node.module.split("."))
                imported_base = ".".join(base_parts)
            else:
                imported_base = node.module or ""
            if imported_base:
                imports.update(f"{imported_base}.{alias.name}" for alias in node.names)
    return imports


def _is_forbidden_contract_import(imported: str) -> bool:
    return any(imported == root or imported.startswith(f"{root}.") for root in FORBIDDEN_CONTRACT_IMPORT_ROOTS)


def _is_runtime_project_import_allowed(imported: str) -> bool:
    return any(imported == root or imported.startswith(f"{root}.") for root in RUNTIME_ALLOWED_PROJECT_IMPORTS)


def _contract_dependency_violations(relative: str, imports: set[str]) -> list[str]:
    violations: list[str] = []
    for imported in sorted(imports):
        root_name = imported.split(".", 1)[0]
        if imported.endswith(".*"):
            violations.append(imported)
            continue
        if relative == "backend/src/domain/harness_contracts.py":
            if (
                imported == "src"
                or imported.startswith("src.")
                or (
                    root_name not in sys.stdlib_module_names
                    and root_name not in ALLOWED_CONTRACT_THIRD_PARTY_ROOTS
                )
            ):
                violations.append(imported)
        elif relative == "backend/src/application/runtime_contracts.py":
            if imported == "src" or imported.startswith("src."):
                if not _is_runtime_project_import_allowed(imported):
                    violations.append(imported)
            elif root_name not in sys.stdlib_module_names and root_name not in ALLOWED_CONTRACT_THIRD_PARTY_ROOTS:
                violations.append(imported)
        if _is_forbidden_contract_import(imported) and imported not in violations:
            violations.append(imported)
    return violations


def _inspect_production_module(relative: str, source_label: str, blob: bytes) -> list[str]:
    source = _decode_python(blob, relative)
    try:
        tree = ast.parse(source, filename=relative)
    except SyntaxError as exc:
        raise GateError(f"无法解析生产模块：{relative}:{exc.lineno or 0} ({source_label})") from exc
    module = ".".join(PurePosixPath(relative).with_suffix("").parts[1:])
    imports = _imports_from_tree(tree, module)
    violations: list[str] = []
    if any(
        imported == "src.application.runtime_contracts"
        or imported.startswith("src.application.runtime_contracts.")
        for imported in imports
    ):
        violations.append(f"{module} -> src.application.runtime_contracts ({source_label})")
    if module != "src.application.runtime_contracts" and any(
        imported == "src.domain.harness_contracts" or imported.startswith("src.domain.harness_contracts.")
        for imported in imports
    ):
        violations.append(f"{module} -> src.domain.harness_contracts ({source_label})")
    if relative in CONTRACT_MODULE_PATHS:
        violations.extend(
            f"{module} -> {imported} ({source_label})"
            for imported in _contract_dependency_violations(relative, imports)
        )
    return violations


def _verify_import_boundaries(root: Path) -> None:
    src_root = root / "backend" / "src"
    violations: list[str] = []
    for path in sorted(src_root.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        violations.extend(_inspect_production_module(relative, "checkout", path.read_bytes()))
    for relative in CONTRACT_MODULE_PATHS:
        for source_label, blob in _candidate_blobs(root, relative):
            if source_label != "checkout":
                violations.extend(_inspect_production_module(relative, source_label, blob))
    if violations:
        raise GateError(f"Harness import 边界被破坏：{'; '.join(sorted(set(violations)))}")


def _profile_history(root: Path, revision: str) -> dict[str, str]:
    return {
        path: _git_blob_sha(root, revision, path)
        for path in _git_paths(root, revision, "backend/tests/fixtures/harness")
        if PROFILE_PATTERN.fullmatch(path)
    }


def _working_profile_paths(root: Path, revision: str) -> list[str]:
    tracked = {path for path in _git_paths(root, revision, "backend/tests/fixtures/harness") if PROFILE_PATTERN.fullmatch(path)}
    tracked.update(
        path
        for path in _line_paths(
            str(
                _run_git(
                    root,
                    "ls-files",
                    "--",
                    "backend/tests/fixtures/harness",
                    text=True,
                )
            )
        )
        if PROFILE_PATTERN.fullmatch(path)
    )
    fixture_dir = root / "backend" / "tests" / "fixtures" / "harness"
    if fixture_dir.exists():
        for path in fixture_dir.glob("current_capability_profile.v*.json"):
            relative = path.relative_to(root).as_posix()
            if PROFILE_PATTERN.fullmatch(relative):
                tracked.add(relative)
    return sorted(tracked)


def _verify_profile_ratchet(root: Path, base_sha: str, expected_history: dict[str, str]) -> None:
    actual_base_history = _profile_history(root, base_sha)
    if actual_base_history != expected_history:
        raise GateError("baseline 中的 capability profile 历史与 base commit 不一致")

    head_history = _profile_history(root, "HEAD")
    index_paths = set(
        _line_paths(
            str(
                _run_git(
                    root,
                    "ls-files",
                    "--",
                    "backend/tests/fixtures/harness",
                    text=True,
                )
            )
        )
    )
    unstaged_paths = set(
        _nul_paths(
            bytes(
                _run_git(
                    root,
                    "diff",
                    "--no-renames",
                    "--name-only",
                    "-z",
                    "--",
                    "backend/tests/fixtures/harness",
                )
            )
        )
    )
    for path, expected_sha in expected_history.items():
        if head_history.get(path) != expected_sha:
            raise GateError(f"HEAD 中既有 capability profile 被修改或删除：{path}")
        if path not in index_paths:
            raise GateError(f"Git index 中既有 capability profile 被删除：{path}")
        if _sha256(bytes(_run_git(root, "show", f":{path}"))) != expected_sha:
            raise GateError(f"Git index 中既有 capability profile 被修改：{path}")
        if path in unstaged_paths:
            raise GateError(f"working tree 中既有 capability profile 被修改：{path}")

    current_paths = _working_profile_paths(root, "HEAD")
    immutable_candidates = set(current_paths) | set(expected_history) | {FIRST_PROFILE_PATH}
    for path in sorted(immutable_candidates):
        log = str(
            _run_git(
                root,
                "log",
                "--diff-filter=A",
                "--format=%H",
                "--",
                path,
                text=True,
            )
        )
        additions = [line.strip() for line in log.splitlines() if line.strip()]
        if not additions:
            continue
        original = _git_blob(root, additions[-1], path)
        if path not in head_history or _git_blob(root, "HEAD", path) != original:
            raise GateError(f"已提交 capability profile 被修改或删除：{path}")
        if path not in index_paths or bytes(_run_git(root, "show", f":{path}")) != original:
            raise GateError(f"Git index 中已提交 capability profile 被修改或删除：{path}")
        if path in unstaged_paths:
            raise GateError(f"working tree 中已提交 capability profile 被修改或删除：{path}")

    versions: list[int] = []
    for path in current_paths:
        match = PROFILE_PATTERN.fullmatch(path)
        if match is None:
            continue
        version = int(match.group(1))
        versions.append(version)
        sources = _candidate_blobs(root, path)
        if not sources:
            raise GateError(f"无法读取 capability profile：{path}")
        for source_label, raw in sources:
            try:
                payload = json.loads(raw.decode("utf-8-sig"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise GateError(f"capability profile 不是有效 UTF-8 JSON：{path} ({source_label})") from exc
            profile_version = payload.get("profile_version") if isinstance(payload, dict) else None
            if type(profile_version) is not int or profile_version != version:
                raise GateError(f"capability profile payload 版本与文件名不一致：{path} ({source_label})")

    versions.sort()
    if versions and versions != list(range(1, max(versions) + 1)):
        raise GateError("capability profile 版本必须从 v1 开始连续递增")
    base_versions = sorted(int(PROFILE_PATTERN.fullmatch(path).group(1)) for path in expected_history)
    new_versions = sorted(set(versions) - set(base_versions))
    if new_versions:
        expected_new = list(range((max(base_versions) if base_versions else 0) + 1, max(new_versions) + 1))
        if new_versions != expected_new:
            raise GateError("新增 capability profile 必须紧接 base 历史连续递增")


def _baseline_payload(root: Path, base_sha: str, generator_raw: bytes) -> dict[str, Any]:
    generator_raw_sha = _sha256(generator_raw)
    canonical_sha = _sha256(_canonical_generator_bytes(generator_raw))
    inventory = _diff_inventory(root, base_sha)
    return {
        "schema_version": SCHEMA_VERSION,
        "base_commit_sha": base_sha,
        "openapi_normalized_sha256": _openapi_sha(root),
        "alembic_heads": _alembic_heads(root),
        "dependency_git_blob_sha256": _hash_files(root, base_sha, DEPENDENCY_PATHS),
        "protected_file_git_blob_sha256": _hash_files(root, base_sha, PROTECTED_FILES),
        "protected_tree_aggregate_sha256": {
            prefix: _aggregate_prefix(root, base_sha, prefix) for prefix in PROTECTED_PREFIXES
        },
        "allowed_changes": {
            "exact_paths": sorted(FINAL_ALLOWED_EXACT_PATHS),
            "prefixes": list(FINAL_ALLOWED_PREFIXES),
            "contract_modules": list(CONTRACT_MODULE_PATHS),
            "harness_tests_and_support": list(HARNESS_TEST_PATHS),
        },
        "generator": {
            "path": GENERATOR_PATH,
            "reviewed_raw_sha256": generator_raw_sha,
            "canonical_utf8_lf_sha256": canonical_sha,
            "bootstrap_dirty_inventory": inventory,
        },
        "skip_xfail_inventory": _skip_inventory(root, base_sha),
        "capability_profile_history": _profile_history(root, base_sha),
    }


def _candidate_skip_inventory(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for relative in HARNESS_TEST_PATHS:
        for source_label, blob in _candidate_blobs(root, relative):
            source = _decode_python(blob, relative)
            try:
                tree = ast.parse(source, filename=relative)
            except SyntaxError as exc:
                raise GateError(
                    f"无法解析 Harness 候选文件：{relative}:{exc.lineno or 0} ({source_label})"
                ) from exc
            visitor = _SkipInventoryVisitor(f"{relative} [{source_label}]")
            visitor.visit(tree)
            entries.extend(visitor.entries.values())
    return sorted(
        entries,
        key=lambda item: (
            str(item["file"]),
            int(item["line"]),
            str(item["category"]),
            str(item["entry_kind"]),
        ),
    )


def _require_mapping(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GateError(f"baseline 字段必须是 object：{key}")
    return value


def _assert_equal(label: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise GateError(f"零行为基线不一致：{label}")


def _verify_baseline_immutability(root: Path, baseline_raw: bytes) -> bool:
    log = str(
        _run_git(
            root,
            "log",
            "--diff-filter=A",
            "--format=%H",
            "--",
            BASELINE_PATH,
            text=True,
        )
    )
    additions = [line.strip() for line in log.splitlines() if line.strip()]
    if not additions:
        if baseline_raw != _canonical_baseline_checkout_bytes(baseline_raw):
            raise GateError("首次提交前的 zero-behavior baseline 必须是无 BOM UTF-8/LF canonical bytes")
        index_paths = set(
            _nul_paths(bytes(_run_git(root, "ls-files", "-z", "--", BASELINE_PATH)))
        )
        if BASELINE_PATH in index_paths:
            index_blob = bytes(_run_git(root, "show", f":{BASELINE_PATH}"))
            if index_blob != baseline_raw:
                raise GateError("首次提交前 baseline 的 Git index 与 checkout 不一致")
        return False
    first_addition = additions[-1]
    original = _git_blob(root, first_addition, BASELINE_PATH)
    if original != _canonical_baseline_checkout_bytes(original):
        raise GateError("首次提交的 zero-behavior baseline blob 不是 UTF-8/LF canonical bytes")
    if _canonical_baseline_checkout_bytes(baseline_raw) != original:
        raise GateError("zero-behavior baseline 在首次提交后被修改")
    try:
        current = _git_blob(root, "HEAD", BASELINE_PATH)
    except GateError as exc:
        raise GateError("已提交 baseline 当前不在 HEAD 中") from exc
    if current != original:
        raise GateError("HEAD 中的 zero-behavior baseline 不等于首次提交版本")
    index_paths = set(
        _nul_paths(bytes(_run_git(root, "ls-files", "-z", "--", BASELINE_PATH)))
    )
    if BASELINE_PATH not in index_paths:
        raise GateError("Git index 中缺少已提交的 zero-behavior baseline")
    index_blob = bytes(_run_git(root, "show", f":{BASELINE_PATH}"))
    if index_blob != original:
        raise GateError("Git index 中的 zero-behavior baseline 不等于首次提交版本")
    return True


def _verify_generator_hashes(root: Path, generator_data: dict[str, Any], *, baseline_committed: bool) -> None:
    if generator_data.get("path") != GENERATOR_PATH:
        raise GateError("baseline generator path 与固定路径不一致")
    reviewed_raw = generator_data.get("reviewed_raw_sha256")
    if not isinstance(reviewed_raw, str) or not re.fullmatch(r"[0-9a-f]{64}", reviewed_raw):
        raise GateError("baseline generator reviewed raw SHA-256 无效")
    expected = generator_data.get("canonical_utf8_lf_sha256")
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise GateError("baseline generator canonical SHA-256 无效")
    raw = (root / GENERATOR_PATH).read_bytes()
    if not baseline_committed:
        _assert_equal("首次提交前 generator reviewed raw SHA-256", _sha256(raw), reviewed_raw)
    canonical = _canonical_generator_bytes(raw)
    _assert_equal("generator canonical SHA-256", _sha256(canonical), expected)

    index_paths = set(_line_paths(str(_run_git(root, "ls-files", GENERATOR_PATH, text=True))))
    if GENERATOR_PATH in index_paths:
        index_blob = bytes(_run_git(root, "show", f":{GENERATOR_PATH}"))
        if index_blob != _canonical_generator_bytes(index_blob):
            raise GateError("generator 的 Git index blob 必须是无 BOM UTF-8/LF canonical bytes")
        _assert_equal("generator index blob SHA-256", _sha256(index_blob), expected)
    if GENERATOR_PATH in set(_git_paths(root, "HEAD", GENERATOR_PATH)):
        head_blob = _git_blob(root, "HEAD", GENERATOR_PATH)
        if head_blob != _canonical_generator_bytes(head_blob):
            raise GateError("generator 的 HEAD blob 必须是无 BOM UTF-8/LF canonical bytes")
        _assert_equal("generator HEAD blob SHA-256", _sha256(head_blob), expected)


def verify(root: Path) -> None:
    baseline_file = root / BASELINE_PATH
    if not baseline_file.is_file():
        raise GateError(f"zero-behavior baseline 尚不存在：{BASELINE_PATH}")
    baseline_raw = baseline_file.read_bytes()
    try:
        payload = json.loads(baseline_raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GateError("zero-behavior baseline 不是有效 UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise GateError("zero-behavior baseline 顶层必须是 object")
    _assert_equal("schema version", payload.get("schema_version"), SCHEMA_VERSION)

    base_sha = payload.get("base_commit_sha")
    if not isinstance(base_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", base_sha):
        raise GateError("baseline base_commit_sha 无效")
    _assert_full_commit(root, base_sha)
    ancestor = subprocess.run(
        [_git_executable(), "merge-base", "--is-ancestor", base_sha, "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if ancestor.returncode != 0:
        raise GateError("baseline base commit 不是当前 HEAD 的祖先")

    inventory = _diff_inventory(root, base_sha)
    _assert_allowed_inventory(inventory, bootstrap=False)
    baseline_committed = _verify_baseline_immutability(root, baseline_raw)

    expected_dependencies = _require_mapping(payload, "dependency_git_blob_sha256")
    expected_protected = _require_mapping(payload, "protected_file_git_blob_sha256")
    expected_aggregates = _require_mapping(payload, "protected_tree_aggregate_sha256")
    _assert_equal(
        "dependency Git blobs",
        _hash_files(root, "HEAD", DEPENDENCY_PATHS),
        expected_dependencies,
    )
    _assert_equal(
        "protected production Git blobs",
        _hash_files(root, "HEAD", PROTECTED_FILES),
        expected_protected,
    )
    _assert_equal(
        "protected tree aggregates",
        {prefix: _aggregate_prefix(root, "HEAD", prefix) for prefix in PROTECTED_PREFIXES},
        expected_aggregates,
    )
    _assert_equal("normalized OpenAPI", _openapi_sha(root), payload.get("openapi_normalized_sha256"))
    _assert_equal("Alembic heads", _alembic_heads(root), payload.get("alembic_heads"))
    _assert_equal("skip/xfail inventory", _skip_inventory(root, "HEAD"), payload.get("skip_xfail_inventory"))

    generator_data = _require_mapping(payload, "generator")
    _verify_generator_hashes(root, generator_data, baseline_committed=baseline_committed)
    if not baseline_committed:
        recorded_inventory = generator_data.get("bootstrap_dirty_inventory")
        expected_categories = {"committed", "staged", "unstaged", "untracked"}
        if not isinstance(recorded_inventory, dict) or set(recorded_inventory) != expected_categories:
            raise GateError("baseline generator bootstrap dirty inventory 无效")
        normalized_recorded: dict[str, list[str]] = {}
        for category in sorted(expected_categories):
            paths = recorded_inventory.get(category)
            if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
                raise GateError("baseline generator bootstrap dirty inventory 条目无效")
            normalized = sorted({_normalize_path(path) for path in paths})
            if normalized != paths:
                raise GateError("baseline generator bootstrap dirty inventory 必须规范化、排序且去重")
            normalized_recorded[category] = normalized
        _assert_allowed_inventory(normalized_recorded, bootstrap=True)
        current_without_baseline = _inventory_union(inventory) - {BASELINE_PATH}
        if not _inventory_union(normalized_recorded).issubset(current_without_baseline):
            raise GateError("首次提交前 bootstrap 捕获路径不再存在于当前四集合")
    _assert_equal(
        "allowed change declaration",
        _require_mapping(payload, "allowed_changes"),
        {
            "exact_paths": sorted(FINAL_ALLOWED_EXACT_PATHS),
            "prefixes": list(FINAL_ALLOWED_PREFIXES),
            "contract_modules": list(CONTRACT_MODULE_PATHS),
            "harness_tests_and_support": list(HARNESS_TEST_PATHS),
        },
    )
    _verify_import_boundaries(root)

    history_raw = _require_mapping(payload, "capability_profile_history")
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in history_raw.items()):
        raise GateError("baseline capability_profile_history 无效")
    _verify_profile_ratchet(root, base_sha, {str(key): str(value) for key, value in history_raw.items()})

    candidate_skip = _candidate_skip_inventory(root)
    if candidate_skip:
        raise GateError("Harness 候选测试/support 中禁止出现 skip、xfail 或 importorskip")


def write_baseline(root: Path, supplied_base_sha: str, reviewed_raw_sha: str) -> None:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", reviewed_raw_sha):
        raise GateError("--reviewed-generator-raw-sha256 必须是 64 位十六进制 SHA-256")
    base_sha = _assert_full_commit(root, supplied_base_sha)
    if _head_sha(root) != base_sha:
        raise GateError("写入 baseline 时 HEAD 必须精确等于 --base-sha")

    baseline_file = root / BASELINE_PATH
    if baseline_file.exists():
        raise GateError("zero-behavior baseline 已存在；禁止刷新或覆盖")
    generator_file = root / GENERATOR_PATH
    if not generator_file.is_file():
        raise GateError("bootstrap generator 文件不存在")
    generator_raw = generator_file.read_bytes()
    actual_raw_sha = _sha256(generator_raw)
    if actual_raw_sha.lower() != reviewed_raw_sha.lower():
        raise GateError("generator 当前 raw SHA-256 与独立 Review 记录不一致")

    inventory = _diff_inventory(root, base_sha)
    _assert_allowed_inventory(inventory, bootstrap=True)
    payload = _baseline_payload(root, base_sha, generator_raw)
    if generator_file.read_bytes() != generator_raw:
        raise GateError("generator 在 baseline payload 计算期间发生变化")
    final_prewrite_inventory = _diff_inventory(root, base_sha)
    if final_prewrite_inventory != inventory:
        raise GateError("bootstrap 四集合在 baseline payload 计算期间发生变化")
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    baseline_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        stream = baseline_file.open("xb")
    except FileExistsError as exc:
        raise GateError("zero-behavior baseline 在写入前已出现；拒绝覆盖") from exc
    except OSError as exc:
        raise GateError("无法安全创建 zero-behavior baseline") from exc

    try:
        with stream:
            stream.write(encoded)
        if generator_file.read_bytes() != generator_raw:
            raise GateError("generator 在 baseline 写入期间发生变化")
        postwrite_inventory = _diff_inventory(root, base_sha)
        postwrite_paths = _inventory_union(postwrite_inventory)
        allowed_postwrite = set(BOOTSTRAP_ALLOWED_PATHS) | {BASELINE_PATH}
        rejected_postwrite = sorted(postwrite_paths - allowed_postwrite)
        if rejected_postwrite or BASELINE_PATH not in postwrite_paths:
            detail = ", ".join(rejected_postwrite) if rejected_postwrite else "baseline 未进入四集合"
            raise GateError(f"baseline 写入后的 bootstrap 四集合无效：{detail}")
        verify(root)
    except BaseException as exc:
        try:
            baseline_file.unlink(missing_ok=True)
        except OSError as cleanup_exc:
            raise GateError("baseline 失败且无法清理未完成文件") from cleanup_exc
        if isinstance(exc, OSError):
            raise GateError("baseline 写入或复验失败，未完成文件已清理") from exc
        raise


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成或校验 P10 Harness 零行为基线")
    parser.add_argument("--write-baseline", action="store_true", help="显式执行首次且唯一的 baseline 写入")
    parser.add_argument("--base-sha", help="经确认的完整 base commit SHA")
    parser.add_argument(
        "--reviewed-generator-raw-sha256",
        help="独立 Reviewer 对当前 checkout generator 原始字节计算的 SHA-256",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        root = _repo_root()
        if args.write_baseline:
            if not args.base_sha or not args.reviewed_generator_raw_sha256:
                raise GateError("写模式必须同时提供 --base-sha 与 --reviewed-generator-raw-sha256")
            write_baseline(root, args.base_sha, args.reviewed_generator_raw_sha256)
            print(f"PASS: 已生成并复验 {BASELINE_PATH}")  # noqa: T201
            return 0
        if args.base_sha or args.reviewed_generator_raw_sha256:
            raise GateError("--base-sha 和 reviewed hash 只允许与 --write-baseline 同时使用")
        verify(root)
        print("PASS: Harness 零行为基线校验通过")  # noqa: T201
        return 0
    except GateError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    except Exception:
        print("FAIL: Harness 零行为工具发生未公开的内部错误", file=sys.stderr)  # noqa: T201
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
