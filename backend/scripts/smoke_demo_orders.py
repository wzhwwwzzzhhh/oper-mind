"""PostgreSQL 订单慢 SQL 靶场的正常、故障、恢复 smoke。"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

try:
    from scripts import demo_orders_env
except ModuleNotFoundError:  # 允许直接通过文件路径执行脚本。
    import demo_orders_env


def main(argv: Sequence[str] | None = None) -> int:
    """执行 Work 1 全流程；默认总会清理专用 schema 和本地服务。"""
    parser = argparse.ArgumentParser(description="OperMind PostgreSQL 订单慢 SQL 靶场 smoke")
    parser.add_argument("--samples", type=int, default=12, help="每个观测窗口的探测次数")
    parser.add_argument("--keep", action="store_true", help="保留靶场现场供人工检查")
    parser.add_argument("--startup-timeout-seconds", type=int, default=30)
    args = parser.parse_args(argv)

    steps = (
        ("start", ["start", "--samples", str(args.samples), "--startup-timeout-seconds", str(args.startup_timeout_seconds)]),
        ("inject", ["inject", "--samples", str(args.samples)]),
        ("verify_degraded", ["verify", "--phase", "degraded"]),
        ("repair", ["repair", "--samples", str(args.samples)]),
        ("verify_recovered", ["verify", "--phase", "recovered"]),
    )
    results: list[dict[str, object]] = []
    exit_code = 0
    try:
        for name, command in steps:
            step_exit_code = demo_orders_env.main(command)
            results.append({"step": name, "exit_code": step_exit_code})
            if step_exit_code != 0:
                exit_code = step_exit_code
                break
    except (OSError, RuntimeError, ValueError) as error:
        results.append({"step": "unexpected_error", "exit_code": 1, "message": str(error)})
        exit_code = 1
    finally:
        if not args.keep:
            clean_exit_code = demo_orders_env.main(["clean"])
            results.append({"step": "clean", "exit_code": clean_exit_code})
            if exit_code == 0 and clean_exit_code != 0:
                exit_code = clean_exit_code

    status = "passed" if exit_code == 0 else "failed"
    sys.stdout.write(json.dumps({"status": status, "steps": results}, ensure_ascii=False, indent=2) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
