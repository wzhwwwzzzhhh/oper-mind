"""模型连通性探针 —— 对诊断模型与裁判模型各发一发最小调用，报通/不通。

用法：
    python scripts/check_models.py            # 测诊断 + 裁判两个模型
    python scripts/check_models.py --diag     # 只测诊断模型
    python scripts/check_models.py --judge    # 只测裁判模型

用于真实跑批前确认通道可用，避免因模型名/额度问题白烧整批。
只发一句极小 prompt，成本极低。设计见 M5 step4。
"""

import argparse
import os
import sys

try:
    from scripts._bootstrap import bootstrap_import_paths
except ModuleNotFoundError:
    from _bootstrap import bootstrap_import_paths

bootstrap_import_paths()

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src.config import load_config
from src.core.llm import LLMClient


def _probe(label: str, api_key: str, base_url: str, model: str) -> bool:
    """对单个模型发一发最小调用；返回是否连通。"""
    print(f"\n[{label}] model={model}  base_url={base_url}")
    if not api_key or api_key == "mock":
        print(f"  ⚠️  跳过：api_key 为空或 mock（当前非真实模式）")
        return False

    client = LLMClient(api_key=api_key, base_url=base_url, model=model)
    resp = client.chat([{"role": "user", "content": "只回复两个字：可以"}], temperature=0.0)

    if "error" in resp:
        print(f"  ❌ 不通：{resp['error']}")
        return False
    content = (resp.get("content") or "").strip()
    print(f"  ✅ 通：返回={content[:40]!r}  累计token={client.total_tokens}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="模型连通性探针")
    parser.add_argument("--diag", action="store_true", help="只测诊断模型")
    parser.add_argument("--judge", action="store_true", help="只测裁判模型")
    args = parser.parse_args()

    # 未指定则两个都测
    test_diag = args.diag or not (args.diag or args.judge)
    test_judge = args.judge or not (args.diag or args.judge)

    config = load_config()
    results: list[bool] = []

    if test_diag:
        llm = config.get("llm", {})
        results.append(_probe("诊断模型", llm.get("api_key", ""), llm.get("base_url", ""), llm.get("model", "")))
    if test_judge:
        jd = config.get("judge_llm", {})
        results.append(_probe("裁判模型", jd.get("api_key", ""), jd.get("base_url", ""), jd.get("model", "")))

    ok = all(results) if results else False
    print(f"\n{'✅ 全部连通，可真实跑批' if ok else '❌ 有模型不通，请先处理再跑批'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
