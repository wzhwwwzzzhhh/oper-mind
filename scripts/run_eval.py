"""评测 Harness CLI 入口 —— 跑数据集过 coordinator，落盘结果。

用法：
    python scripts/run_eval.py            # mock 模式（默认，config.local.yaml 未配置真实 key 时自动走 mock）
    python scripts/run_eval.py --real     # 强制要求非 mock（若仍解析出 mock key 则报错退出）
    python scripts/run_eval.py --cases path/to/cases.jsonl --seed 42

产出 experiments/<config_hash>/{summary.json, cases.jsonl, meta.json}。
设计见 docs/开发/M2-评测Harness/design.md 第 4 节。
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from data.eval.validate import load_cases
from src.core.bootstrap import build_judge_llm, build_system
from src.core.experiment import get_experiment_condition, supported_arms
from src.eval.result_schema import CaseResult, build_summary
from src.eval.runner import run_suite

DEFAULT_CASES = os.path.join(_ROOT, "data", "eval", "cases.jsonl")
EXPERIMENTS_DIR = os.path.join(_ROOT, "experiments")


def _is_mock_llm(coordinator) -> bool:
    """判断被测 LLM 是否处于 mock 模式（api_key == 'mock'）"""
    return getattr(getattr(coordinator.llm, "client", None), "api_key", None) == "mock"


def _config_hash(
    cases_path: str,
    seed: int,
    is_mock: bool,
    model: str,
    judge_model: str,
    arm: str,
    replicate: int,
) -> str:
    """对数据集、模型、裁判模型、实验组和重复编号做哈希。"""
    fingerprint = f"{os.path.abspath(cases_path)}|{seed}|{is_mock}|{model}|{judge_model}|{arm}|{replicate}"
    return hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:12]


def main() -> None:
    parser = argparse.ArgumentParser(description="OperMind 评测 Harness")
    parser.add_argument("--cases", default=DEFAULT_CASES, help="评测用例 jsonl 路径")
    parser.add_argument("--seed", type=int, default=42, help="随机种子（保证复现）")
    parser.add_argument("--real", action="store_true", help="要求非 mock 模式；若仍是 mock 则报错退出")
    parser.add_argument("--arm", choices=supported_arms(), default="full", help="M4 实验组")
    parser.add_argument("--replicate", type=int, choices=(1, 2, 3), default=1, help="重复运行编号")
    args = parser.parse_args()

    random.seed(args.seed)

    cases, load_errors = load_cases(args.cases)
    if load_errors:
        print(f"❌ 数据集加载有误，共 {len(load_errors)} 条错误：")
        for e in load_errors:
            print("  -", e)
        sys.exit(1)
    # 评测样例必须独立，禁止读取或写入长期记忆。
    experiment_condition = get_experiment_condition(args.arm)
    coordinator = build_system(
        enable_long_term_memory=False,
        experiment_condition=experiment_condition,
    )
    is_mock = _is_mock_llm(coordinator)
    judge_llm = coordinator.llm if is_mock else build_judge_llm()

    if args.real and is_mock:
        print("❌ --real 要求非 mock 模式，但当前配置解析出的仍是 mock LLM。请检查 OPERMIND_API_KEY / config.local.yaml。")
        sys.exit(1)

    print(f"[run_eval] 用例数={len(cases)}  mock={is_mock}  model={coordinator.llm.model}")

    started = time.time()
    raw_results = run_suite(coordinator, judge_llm, cases)
    duration = time.time() - started

    case_results = [
        CaseResult.from_run_result(case, raw)
        for case, raw in zip(cases, raw_results)
    ]
    judge_model = "mock_stub" if is_mock else judge_llm.model
    config_hash = _config_hash(
        args.cases, args.seed, is_mock, coordinator.llm.model, judge_model, args.arm, args.replicate
    )
    summary = build_summary(config_hash, case_results)

    out_dir = os.path.join(EXPERIMENTS_DIR, config_hash)
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "cases.jsonl"), "w", encoding="utf-8") as f:
        for r in case_results:
            f.write(r.model_dump_json() + "\n")

    with open(os.path.join(out_dir, "summary.json"), "w", encoding="utf-8") as f:
        f.write(summary.model_dump_json(indent=2))

    meta = {
        "config_hash": config_hash,
        "cases_path": os.path.abspath(args.cases),
        "seed": args.seed,
        "is_mock": is_mock,
        "model": coordinator.llm.model,
        "judge_model": judge_model,
        "arm": args.arm,
        "replicate": args.replicate,
        "total_cases": len(cases),
        "duration_seconds": round(duration, 2),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"\n[run_eval] 完成，用时 {duration:.1f}s，产出目录：{out_dir}")
    print(f"  route_hit_rate       = {summary.route_hit_rate:.2%}")
    print(f"  target_hit_rate      = {summary.target_hit_rate:.2%}")
    print(f"  pipeline_complete    = {summary.pipeline_complete_rate:.2%}")
    print(f"  condition_complete   = {summary.condition_complete_rate:.2%}")
    print(f"  mechanism_hit_rate   = {summary.mechanism_hit_rate:.2%}")
    print(f"  mean_root_cause      = {summary.mean_root_cause_score:.3f}")
    print(f"  mean_key_points      = {summary.mean_key_points_recall:.3f}")
    print(f"  mean_latency_ms      = {summary.mean_latency_ms:.1f}")
    print(f"  judge_is_stub        = {summary.judge_is_stub}")
    print(f"  error_count          = {summary.error_count}")


if __name__ == "__main__":
    main()
