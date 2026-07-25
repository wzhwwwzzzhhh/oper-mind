"""系统装配 — 统一构建 Coordinator 及其依赖

app.py（FastAPI 入口）与 main.py（CLI 入口）此前各自维护了一份逐字重复的
build_system()。为消除重复、保证两个入口的装配逻辑单一可信，将构建逻辑集中到此处。
"""

from src.core.experiment import ExperimentCondition
from src.core.llm import LLMClient
from src.core.coordinator import CoordinatorAgent
from src.agents.db_agent import DBAgent
from src.agents.server_agent import ServerAgent
from src.agents.log_agent import LogAgent
from src.agents.report_agent import ReportAgent
from src.core.debate import DebateArena
from src.core.reflection import ReflectionEngine
from src.config import load_config
from data.scenarios import set_active_scenario, clear_active_scenario


def build_system(
    enable_long_term_memory: bool = True,
    experiment_condition: ExperimentCondition | None = None,
) -> CoordinatorAgent:
    """构建整个系统；评测可关闭长期记忆并注入实验条件。"""
    config = load_config()
    llm_config = config["llm"]

    llm = LLMClient(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model=llm_config.get("model", "qwen2.5:7b"),
    )

    # mock 模式激活确定性场景（默认 S1）；真实模式清除，工具走真实数据源（如 psutil）
    if llm_config["api_key"] == "mock":
        set_active_scenario("S1")
    else:
        clear_active_scenario()

    # 领域 Agent
    db_agent = DBAgent(llm=llm, enable_long_term_memory=enable_long_term_memory)
    server_agent = ServerAgent(llm=llm, enable_long_term_memory=enable_long_term_memory)
    log_agent = LogAgent(llm=llm, enable_long_term_memory=enable_long_term_memory)

    # 质量保障组件
    debate = DebateArena(llm=llm)
    reflection = ReflectionEngine(llm=llm)
    report = ReportAgent()

    # Coordinator：持有编排图，注入领域 Agent 与质量保障组件
    coordinator = CoordinatorAgent(
        llm=llm,
        debate=debate,
        reflection=reflection,
        report=report,
        experiment_condition=experiment_condition,
    )
    coordinator.register_agent("db", db_agent)
    coordinator.register_agent("server", server_agent)
    coordinator.register_agent("log", log_agent)
    return coordinator


def build_judge_llm() -> LLMClient:
    """构建真实评测使用的独立裁判模型客户端。"""
    config = load_config(require_judge_llm=True)
    judge_config = config["judge_llm"]
    return LLMClient(
        api_key=judge_config["api_key"],
        base_url=judge_config["base_url"],
        model=judge_config["model"],
    )
