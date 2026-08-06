"""LangGraph 编排图 —— 多智能体协作诊断的主编排层。

把"路由 → 领域 Agent(并发) → Debate → Report → Reflection"这条协作链
表达成一张状态图。领域 Agent 内部仍是手搓 ReAct(BaseAgent.run),这里只负责编排。

设计要点见 docs/初始开发/11-质量保障pipeline接通与LangGraph编排.md。
"""

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

from src.core.llm import LLMClient


# ===== 1. 状态定义 =====

class DiagnosisState(TypedDict, total=False):
    """在图节点之间传递的状态"""
    query: str                     # 用户原始问题
    strategy: str                  # direct / chain / parallel
    target: str                    # direct 模式命中的目标 Agent
    agent_results: dict            # {agent 名: 诊断结论}
    agent_thinking: dict           # {agent 名: 思考链路}
    has_conflict: bool             # 并行结论是否分歧
    debate_result: str             # 辩论共识
    report_draft: str              # 报告初稿
    review_feedback: list          # Reflection 复审反馈
    final_report: str              # 终稿
    revision_count: int            # 复审回退次数(防死循环)
    trace: list                    # 全链路事件流(给前端可视化)


MAX_REVISION = 2   # Reflection 回退修订上限,防止死循环


# ===== 2. 工具函数:关键词兜底路由 =====

_SQL_KW = ["select", "from", "where", "join", "explain", "sql", "索引", "慢查询", "慢sql"]
_SERVER_KW = ["cpu", "内存", "磁盘", "进程", "负载", "服务器", "线程", "network", "网络"]
_LOG_KW = ["日志", "错误", "异常", "报错", "log", "timeout", "超时"]
# 全面体检 → 并行;模糊卡慢 → 链式逐层排查
_PARALLEL_KW = ["体检", "全面", "整体", "健康", "大促", "巡检", "上线前"]
_CHAIN_KW = ["很慢", "卡", "故障", "排查", "定位", "慢", "不稳定"]


def _keyword_strategy(user_input: str) -> str:
    """LLM 不可用时的兜底:关键词判断路由策略"""
    text = user_input.lower()
    is_sql = any(k in text for k in _SQL_KW)
    is_server = any(k in text for k in _SERVER_KW)
    is_log = any(k in text for k in _LOG_KW)
    hits = sum([is_sql, is_server, is_log])

    if any(k in text for k in _PARALLEL_KW):
        return "parallel"
    if any(k in text for k in _CHAIN_KW) or hits >= 2:
        return "chain"
    return "direct"


def _keyword_target(user_input: str) -> str | None:
    """关键词识别 direct 模式的目标 Agent"""
    text = user_input.lower()
    if any(k in text for k in _SQL_KW):
        return "db"
    if any(k in text for k in _SERVER_KW):
        return "server"
    if any(k in text for k in _LOG_KW):
        return "log"
    return None


def _is_mock(llm: LLMClient) -> bool:
    """是否处于 mock 模式(api_key=='mock')"""
    return getattr(getattr(llm, "client", None), "api_key", None) == "mock"


def _extract_json(text: str) -> dict | None:
    """从 LLM 返回文本里抠出第一个 JSON 对象"""
    if not text:
        return None
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _tool_traces(agent, role: str | None = None) -> list[dict]:
    """把一个 Agent 本次 run 的工具调用审计记录转成 trace 事件字典。"""
    getter = getattr(agent, "get_tool_invocations", None)
    records = getter() if callable(getter) else []
    return [
        {
            "node": "tool",
            "detail": r.detail,
            "status": r.status,
            "duration_ms": r.duration_ms,
            **({"role": role} if role is not None else {}),
        }
        for r in records
    ]


# ===== 3. 编排图构建 =====

def build_diagnosis_graph(
    llm: LLMClient,
    agents: dict,
    debate,
    reflection,
    report,
):
    """构建并编译诊断编排图。

    Args:
        llm: LLM 客户端
        agents: {"db": DBAgent, "server": ServerAgent, "log": LogAgent}
        debate: DebateArena 实例
        reflection: ReflectionEngine 实例
        report: ReportAgent 实例

    Returns:
        编译后的 LangGraph app,通过 .invoke(state) 运行。
    """

    # ---- 节点:LLM 路由决策(带关键词兜底) ----
    def route_node(state: DiagnosisState) -> DiagnosisState:
        query = state["query"]
        trace = state.get("trace", [])

        strategy, target = None, None
        if not _is_mock(llm):
            prompt = f"""你是运维诊断调度器。分析用户问题,决定路由策略。

- direct:问题明确指向单个领域(SQL/数据库、CPU/服务器、日志)
- chain:问题模糊,需要逐层排查(先服务器,再数据库,再日志)
- parallel:需要全面体检多个维度

领域取值:db(数据库/SQL)、server(服务器/CPU/内存)、log(日志)。
用户问题:{query}

只返回 JSON,不要解释,格式:{{"strategy": "direct|chain|parallel", "target": "db|server|log|null"}}"""
            resp = llm.chat([{"role": "user", "content": prompt}], temperature=0.0)
            parsed = _extract_json(resp.get("content", "")) if "error" not in resp else None
            if parsed:
                strategy = parsed.get("strategy")
                target = parsed.get("target")
                if target in ("null", "", None):
                    target = None

        # 兜底:LLM 不可用 / mock / 解析失败
        if strategy not in ("direct", "chain", "parallel"):
            strategy = _keyword_strategy(query)
            trace = trace + [{"node": "route", "detail": f"兜底关键词路由 → {strategy}"}]
        else:
            trace = trace + [{"node": "route", "detail": f"LLM 路由 → {strategy}"}]

        # target 始终表示主要领域，direct 模式据此选择领域 Agent。
        target = target or _keyword_target(query) or "db"

        return {"strategy": strategy, "target": target, "trace": trace}

    # ---- 节点:直达 ----
    def direct_node(state: DiagnosisState) -> DiagnosisState:
        query = state["query"]
        target = state.get("target") or "db"
        trace = state.get("trace", [])

        if target not in agents:
            result = f"未找到可处理的 Agent:{target}"
            thinking = []
        else:
            agent = agents[target]
            result = agent.run(query)
            thinking = agent.get_thinking() if hasattr(agent, "get_thinking") else []
            trace = trace + _tool_traces(agent, target)

        trace = trace + [{"node": "direct", "detail": f"目标 Agent={target}"}]
        return {
            "agent_results": {target: result},
            "agent_thinking": {target: thinking},
            "trace": trace,
        }

    # ---- 节点:链式(逐层,后层带上前层结论) ----
    def chain_node(state: DiagnosisState) -> DiagnosisState:
        query = state["query"]
        trace = state.get("trace", [])
        results, thinking_map = {}, {}
        context = ""

        for name, prompt_prefix in (
            ("server", "检查系统/服务器状态"),
            ("db", "检查数据库状态"),
            ("log", "检索相关日志"),
        ):
            if name not in agents:
                continue
            agent = agents[name]
            sub_query = f"{prompt_prefix}:{query}"
            if context:
                sub_query += f"\n\n【上游诊断线索】\n{context}"
            res = agent.run(sub_query)
            results[name] = res
            thinking_map[name] = agent.get_thinking() if hasattr(agent, "get_thinking") else []
            trace = trace + _tool_traces(agent, name)
            context += f"\n[{name}] {res[:200]}"
            trace = trace + [{"node": "chain", "detail": f"逐层:{name}"}]

        return {"agent_results": results, "agent_thinking": thinking_map, "trace": trace}

    # ---- 节点:并行(真并发) ----
    def parallel_node(state: DiagnosisState) -> DiagnosisState:
        query = state["query"]
        trace = state.get("trace", [])
        names = list(agents.keys())

        def _run(name):
            agent = agents[name]
            res = agent.run(query)
            think = agent.get_thinking() if hasattr(agent, "get_thinking") else []
            tools = _tool_traces(agent, name)   # 线程内取，防止 run 后状态被覆盖
            return name, res, think, tools

        results, thinking_map = {}, {}
        with ThreadPoolExecutor(max_workers=max(1, len(names))) as pool:
            for name, res, think, tools in pool.map(_run, names):
                results[name] = res
                thinking_map[name] = think
                trace = trace + tools

        trace = trace + [{"node": "parallel", "detail": f"并发 Agent={names}"}]
        return {"agent_results": results, "agent_thinking": thinking_map, "trace": trace}

    # ---- 节点:分歧检测 ----
    def conflict_check_node(state: DiagnosisState) -> DiagnosisState:
        results = state.get("agent_results", {})
        trace = state.get("trace", [])
        conflict = False

        valid = {k: v for k, v in results.items() if v and "未找到" not in v}
        if len(valid) >= 2:
            if _is_mock(llm):
                # 启发式:结论文本差异较大即视为分歧
                conclusions = list(valid.values())
                conflict = len({c[:60] for c in conclusions}) > 1
            else:
                view = "\n".join(f"[{k}] {v[:300]}" for k, v in valid.items())
                prompt = f"""下面是多个运维 Agent 对同一问题的诊断结论。
判断它们的根因结论是否存在实质性分歧(而非互补)。
只返回 JSON:{{"conflict": true|false}}

{view}"""
                resp = llm.chat([{"role": "user", "content": prompt}], temperature=0.0)
                parsed = _extract_json(resp.get("content", "")) if "error" not in resp else None
                conflict = bool(parsed.get("conflict")) if parsed else False

        trace = trace + [{"node": "conflict_check", "detail": f"分歧={conflict}"}]
        return {"has_conflict": conflict, "trace": trace}

    # ---- 节点:辩论 ----
    def debate_node(state: DiagnosisState) -> DiagnosisState:
        query = state["query"]
        results = state.get("agent_results", {})
        thinking = state.get("agent_thinking", {})
        trace = state.get("trace", [])

        consensus = debate.debate(query, results, thinking)
        trace = trace + [{"node": "debate", "detail": "辩论裁决完成"}]
        return {"debate_result": consensus, "trace": trace}

    # ---- 节点:报告(初稿 / 据反馈修订) ----
    def report_node(state: DiagnosisState) -> DiagnosisState:
        query = state["query"]
        results = dict(state.get("agent_results", {}))
        feedback = state.get("review_feedback", [])
        trace = state.get("trace", [])

        if state.get("debate_result"):
            results["共识(辩论)"] = state["debate_result"]

        thinking_flat = [
            f"{name}: {step}"
            for name, steps in state.get("agent_thinking", {}).items()
            for step in (steps or [])
        ]

        if feedback:
            # 据 Reflection 反馈修订上一版初稿
            draft = _revise_report(llm, state.get("report_draft", ""), feedback)
            trace = trace + [{"node": "report", "detail": "据复审反馈修订"}]
        else:
            draft = report.generate(query, results, thinking_flat or None)
            trace = trace + [{"node": "report", "detail": "生成初稿"}]

        return {"report_draft": draft, "trace": trace}

    # ---- 节点:反思复审 ----
    def reflection_node(state: DiagnosisState) -> DiagnosisState:
        draft = state.get("report_draft", "")
        trace = state.get("trace", [])
        revision = state.get("revision_count", 0)

        if _is_mock(llm):
            issues = []   # mock 模式下确定性通过,保证链路可测
        else:
            reviewers = list(agents.values())
            issues = reflection.collect_feedback(draft, reviewers)

        if not issues or revision >= MAX_REVISION:
            trace = trace + [{"node": "reflection", "detail": "复审通过" if not issues else "达修订上限,采用当前稿"}]
            return {"final_report": draft, "review_feedback": [], "trace": trace}

        trace = trace + [{"node": "reflection", "detail": f"发现 {len(issues)} 处问题,回退修订"}]
        return {"review_feedback": issues, "revision_count": revision + 1, "trace": trace}

    # ---- 条件边 ----
    def _by_strategy(state: DiagnosisState) -> Literal["direct", "chain", "parallel"]:
        return state.get("strategy", "direct")  # type: ignore[return-value]

    def _after_conflict(state: DiagnosisState) -> Literal["debate", "report"]:
        return "debate" if state.get("has_conflict") else "report"

    def _after_reflection(state: DiagnosisState) -> Literal["report", "__end__"]:
        return "report" if state.get("review_feedback") else END  # type: ignore[return-value]

    # ---- 组装图 ----
    g = StateGraph(DiagnosisState)
    g.add_node("route", route_node)
    g.add_node("direct", direct_node)
    g.add_node("chain", chain_node)
    g.add_node("parallel", parallel_node)
    g.add_node("conflict_check", conflict_check_node)
    g.add_node("debate", debate_node)
    g.add_node("report", report_node)
    g.add_node("reflection", reflection_node)

    g.add_edge(START, "route")
    g.add_conditional_edges("route", _by_strategy, {
        "direct": "direct",
        "chain": "chain",
        "parallel": "parallel",
    })
    g.add_edge("direct", "report")
    g.add_edge("chain", "report")
    g.add_edge("parallel", "conflict_check")
    g.add_conditional_edges("conflict_check", _after_conflict, {
        "debate": "debate",
        "report": "report",
    })
    g.add_edge("debate", "report")
    g.add_edge("report", "reflection")
    g.add_conditional_edges("reflection", _after_reflection, {
        "report": "report",
        END: END,
    })

    return g.compile()


def _revise_report(llm: LLMClient, draft: str, feedback: list) -> str:
    """据复审反馈修订报告初稿"""
    if not draft:
        return draft
    fb = "\n".join(f"- {f}" for f in feedback)
    prompt = f"""请根据以下审核反馈修订诊断报告,输出修订后的完整报告。

原始报告:
{draft}

审核反馈:
{fb}"""
    resp = llm.chat([
        {"role": "system", "content": "你是报告编辑,负责根据反馈修订运维诊断报告。"},
        {"role": "user", "content": prompt},
    ])
    return resp.get("content") or draft
