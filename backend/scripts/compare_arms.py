"""跨实验组对比 —— 读多个 experiments/<hash>/ 汇总，输出 arm 对比表。

用法：
    python scripts/compare_arms.py <config_hash1> <config_hash2> ...

先用 run_eval.py --arm 分别跑各组（single_agent / full / no_debate / no_reflection），
再把各自的 config_hash 传入本脚本，得到「多 Agent vs 单模型」的横向对比：
总均值 + 按用例分组（mislead / conflict / legacy_compound / single_domain）的根因命中分。
设计见 docs/开发/M5-多Agent价值对比/step4-对比实验与指标.md。
"""

import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

EXPERIMENTS_DIR = os.path.join(_ROOT, "experiments")


def _load(config_hash: str) -> tuple[dict, dict] | None:
    """读取一个实验目录的 summary.json 与 meta.json。"""
    base = os.path.join(EXPERIMENTS_DIR, config_hash)
    summary_path = os.path.join(base, "summary.json")
    meta_path = os.path.join(base, "meta.json")
    if not os.path.exists(summary_path):
        print(f"❌ 找不到 {summary_path}")
        return None
    try:
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)
        meta = {}
        if os.path.exists(meta_path):
            with open(meta_path, encoding="utf-8") as f:
                meta = json.load(f)
    except json.JSONDecodeError as error:
        print(f"❌ {config_hash} 的 JSON 解析失败：{error}")
        return None
    return summary, meta


def main() -> int:
    hashes = sys.argv[1:]
    if not hashes:
        print("用法：python scripts/compare_arms.py <config_hash1> <config_hash2> ...")
        return 1

    loaded = [(h, _load(h)) for h in hashes]
    rows = [(h, s, m) for h, (s, m) in ((h, r) for h, r in loaded if r) ]
    if not rows:
        return 1

    # 主对比表：一行一个实验组
    print("\n=== 总体对比（各 arm）===")
    header = f"{'arm':14s} {'model':18s} {'stub':5s} {'根因分':>7s} {'召回':>6s} {'token':>8s} {'延迟ms':>8s}"
    print(header)
    print("-" * len(header))
    for h, s, m in rows:
        arm = m.get("arm", h)
        model = (m.get("model") or "")[:18]
        print(
            f"{arm:14s} {model:18s} {str(s.get('judge_is_stub')):5s} "
            f"{s.get('mean_root_cause_score', 0):7.3f} {s.get('mean_key_points_recall', 0):6.3f} "
            f"{s.get('mean_tokens', 0):8.1f} {s.get('mean_latency_ms', 0):8.1f}"
        )

    # 按用例分组的根因命中分矩阵：行=分组，列=arm（多 Agent 价值主要看 mislead/conflict 行）
    groups = sorted({g for _, s, _ in rows for g in s.get("by_case_group", {})})
    if groups:
        print("\n=== 按用例分组的根因命中分（行=分组，列=arm）===")
        arm_labels = [m.get("arm", h) for h, s, m in rows]
        head = f"{'group':18s}" + "".join(f"{a:>14s}" for a in arm_labels)
        print(head)
        print("-" * len(head))
        for g in groups:
            cells = ""
            for _, s, _ in rows:
                st = s.get("by_case_group", {}).get(g)
                cells += f"{(st['mean_root_cause_score'] if st else 0):>14.3f}"
            print(f"{g:18s}{cells}")

    print("\n提示：多 Agent 价值主要看 mislead / conflict 两行 full 相对 single_agent 的差值。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
