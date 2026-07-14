"""CLI 入口 — 多智能体运维诊断系统"""

from src.core.bootstrap import build_system


def main():
    coordinator = build_system()

    print("=" * 50)
    print("  OperMind — 多智能体运维诊断系统")
    print("=" * 50)
    print("输入问题进行分析，支持以下场景：")
    print("  • SQL 诊断：输入 SELECT/EXPLAIN 等 SQL 语句")
    print("  • 服务器检查：输入 CPU/内存/磁盘/进程相关问题")
    print("  • 日志分析：输入日志/错误/异常相关问题")
    print("  • 综合排查：输入系统卡慢/故障等模糊问题")
    print("输入 'exit' 退出\n")

    while True:
        user_input = input("> ").strip()
        if user_input.lower() in ("exit", "quit", "q"):
            break

        result = coordinator.route(user_input)
        print(f"\n{result}\n")


if __name__ == "__main__":
    main()
