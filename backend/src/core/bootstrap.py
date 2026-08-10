"""系统装配 — 统一构建 Coordinator 及其依赖

app.py（FastAPI 入口）与 main.py（CLI 入口）此前各自维护了一份逐字重复的
build_system()。为消除重复、保证两个入口的装配逻辑单一可信，将构建逻辑集中到此处。
"""

from data.scenarios import clear_active_scenario, set_active_scenario

from src.agents.db_agent import DBAgent
from src.agents.knowledge_agent import KnowledgeAgent
from src.agents.log_agent import LogAgent
from src.agents.report_agent import ReportAgent
from src.agents.server_agent import ServerAgent
from src.config import load_config, load_knowledge_settings
from src.core.coordinator import CoordinatorAgent
from src.core.debate import DebateArena
from src.core.llm import LLMClient
from src.core.reflection import ReflectionEngine


def build_llm_from_config(config: dict) -> LLMClient:
    """从生效模型配置构建 LLM 客户端；配置缺失时回退确定性 mock，永不 raise。"""
    llm_config = config.get("llm") or {}
    api_key = llm_config.get("api_key") or "mock"
    base_url = llm_config.get("base_url") or "http://mock"
    model = llm_config.get("model") or "mock"

    llm = LLMClient(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )

    # mock 模式激活确定性场景（默认 S1）；真实模式清除，工具走真实数据源（如 psutil）
    if api_key == "mock":
        set_active_scenario("S1")
    else:
        clear_active_scenario()
    return llm


def build_llm() -> LLMClient:
    """构建共享 LLM 客户端，并按模式设置确定性 mock 场景。

    LLM 客户端在多个 Run 间可安全共享（无每请求可变状态）；mock 场景开关是
    进程级设置，只需在构建时设定一次，不随每 Run 重复切换。
    """
    return build_llm_from_config(load_config())


def build_coordinator(llm: LLMClient, service_id: str | None = None, enable_long_term_memory: bool = False) -> CoordinatorAgent:
    """用共享 LLM 现造一套内核（领域 Agent + 质量组件 + 协调器）。

    领域 Agent 持有 short_term/thinking 等实例级可变状态，因此必须每 Run 新造
    一套以隔离并发。默认关闭文件型长期记忆，避免多 Run 并发写同一 memory.json。
    """
    db_agent = DBAgent(llm=llm, service_id=service_id, enable_long_term_memory=enable_long_term_memory)
    server_agent = ServerAgent(llm=llm, enable_long_term_memory=enable_long_term_memory)
    log_agent = LogAgent(llm=llm, service_id=service_id, enable_long_term_memory=enable_long_term_memory)
    knowledge_settings = load_knowledge_settings()
    knowledge_agent = KnowledgeAgent(
        llm=llm,
        knowledge_dir=knowledge_settings.directory,
        enable_long_term_memory=enable_long_term_memory,
    )

    debate = DebateArena(llm=llm)
    reflection = ReflectionEngine(llm=llm)
    report = ReportAgent()

    coordinator = CoordinatorAgent(
        llm=llm,
        debate=debate,
        reflection=reflection,
        report=report,
    )
    coordinator.register_agent("db", db_agent)
    coordinator.register_agent("server", server_agent)
    coordinator.register_agent("log", log_agent)
    coordinator.register_agent("knowledge", knowledge_agent)
    return coordinator


def build_system(enable_long_term_memory: bool = True) -> CoordinatorAgent:
    """一次性装配单例内核（旧 /diagnose 等入口使用）。

    正式 v1 路径改用 build_llm + 每 Run build_coordinator 的工厂方式以隔离并发。
    """
    return build_coordinator(build_llm(), enable_long_term_memory=enable_long_term_memory)
