"""CLI 入口 — 多智能体运维诊断系统"""

from src.core.llm import LLMClient
from src.core.coordinator import CoordinatorAgent
from src.agents.db_agent import DBAgent
from src.agents.server_agent import ServerAgent
from src.agents.log_agent import LogAgent
from src.agents.report_agent import ReportAgent
from src.core.debate import DebateArena
from src.core.reflection import ReflectionEngine
from src.config import load_config


def build_system():
    """构建整个系统，注入所有依赖，返回已接通质量保障链路的 Coordinator"""
    config = load_config()
    llm_config = config["llm"]

    llm = LLMClient(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model=llm_config.get("model", "qwen2.5:7b"),
    )

    # 领域 Agent
    db_agent = DBAgent(llm=llm)
    server_agent = ServerAgent(llm=llm)
    log_agent = LogAgent(llm=llm)

    # 质量保障组件
    debate = DebateArena(llm=llm)
    reflection = ReflectionEngine(llm=llm)
    report = ReportAgent()

    # Coordinator：持有编排图，注入领域 Agent 与质量保障组件
    coordinator = CoordinatorAgent(
        llm=llm, debate=debate, reflection=reflection, report=report
    )
    coordinator.register_agent("db", db_agent)
    coordinator.register_agent("server", server_agent)
    coordinator.register_agent("log", log_agent)

    return coordinator


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
