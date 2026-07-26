"""评测数据集校验器 —— 加载 cases.jsonl，逐条过 Pydantic + 路由一致性检查。

两层校验：
1. 结构校验：每条过 EvalCase（字段类型、跨字段约束）。
2. 路由一致性：复用 src/core/graph 的真实关键词路由函数，验证每条 query 在
   mock 模式下确实会命中其 expected_strategy / direct 目标 Agent。
   —— 直接 import 运行时函数而非复制逻辑，保证校验与实际路由同源。

用法：
    python data/eval/validate.py            # 校验默认 cases.jsonl
    python data/eval/validate.py <path>     # 校验指定 jsonl

设计见 docs/开发/M1-评测数据集/design.md。
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path

# 根目录评测脚本的唯一启动桥接：后续路径均由 src.project_paths 提供。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
for path in (PROJECT_ROOT, BACKEND_ROOT):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

from src.project_paths import DATA_DIR

# Windows 控制台默认 GBK，无法编码 emoji；统一重配为 UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from pydantic import ValidationError

from data.eval.schema import EvalCase
from data.scenarios import supported_scenarios
from src.core.graph import _keyword_strategy, _keyword_target

DEFAULT_CASES = str(DATA_DIR / "eval" / "cases.jsonl")


def load_cases(path: str) -> tuple[list[EvalCase], list[str]]:
    """加载并结构校验 jsonl。返回（合法用例列表，错误信息列表）"""
    cases: list[EvalCase] = []
    errors: list[str] = []

    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"第 {lineno} 行 JSON 解析失败：{e}")
                continue
            try:
                cases.append(EvalCase(**raw))
            except ValidationError as e:
                cid = raw.get("case_id", f"第{lineno}行")
                errors.append(f"[{cid}] 结构校验失败：{e.errors()}")

    return cases, errors


def check_routing(cases: list[EvalCase]) -> list[str]:
    """路由一致性：复用运行时关键词路由，验证 query 能命中 expected_strategy。"""
    errors: list[str] = []
    for c in cases:
        got = _keyword_strategy(c.query)
        if got != c.expected_strategy:
            errors.append(
                f"[{c.case_id}] 路由不一致：query 关键词命中 '{got}'，"
                f"但 expected_strategy='{c.expected_strategy}'。query={c.query!r}"
            )
        # direct 还要校验目标 Agent 命中
        if c.expected_strategy == "direct":
            target = _keyword_target(c.query) or "db"
            if target != c.expected_agents[0]:
                errors.append(
                    f"[{c.case_id}] direct 目标不一致：关键词命中 '{target}'，"
                    f"但 expected_agents[0]='{c.expected_agents[0]}'。query={c.query!r}"
                )
    return errors


def check_scenarios(cases: list[EvalCase]) -> list[str]:
    """场景合法性：scenario 必须是 data/scenarios.py 注册的 key。"""
    valid = set(supported_scenarios())
    errors: list[str] = []
    for c in cases:
        if c.scenario not in valid:
            errors.append(
                f"[{c.case_id}] 未知场景 scenario='{c.scenario}'，合法：{sorted(valid)}"
            )
    return errors


def print_distribution(cases: list[EvalCase]) -> None:
    """打印领域 / 策略 / 难度 / 来源 / 场景 / debate 分布统计"""
    print(f"\n用例总数：{len(cases)}")
    for field in ("domain", "expected_strategy", "difficulty", "source", "scenario"):
        dist = Counter(getattr(c, field) for c in cases)
        pretty = "，".join(f"{k}={v}" for k, v in sorted(dist.items()))
        print(f"  {field:18s}: {pretty}")
    debate_n = sum(1 for c in cases if c.expects_debate)
    print(f"  {'expects_debate':18s}: true={debate_n}")


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CASES
    if not os.path.exists(path):
        print(f"❌ 找不到用例文件：{path}")
        return 1

    cases, struct_errors = load_cases(path)
    routing_errors = check_routing(cases)
    scenario_errors = check_scenarios(cases)
    all_errors = struct_errors + routing_errors + scenario_errors

    print_distribution(cases)

    if all_errors:
        print(f"\n❌ 校验失败，共 {len(all_errors)} 处问题：")
        for e in all_errors:
            print("  -", e)
        return 1

    print(f"\n✅ 校验通过：{len(cases)} 条用例全部合法，路由与运行时一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
