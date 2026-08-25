"""Debate Arena — 多 Agent 辩论引擎

当多个 Agent 对同一问题给出不一致的诊断结论时，
组织辩论让各方提供证据，最终达成共识。
"""

from src.core.llm import LLMClient


class DebateArena:
    """
    辩论场。

    流程：
    1. 收集各 Agent 的诊断结论
    2. 列出分歧点
    3. 各方辩护（提供证据）
    4. 投票或由 Coordinator 裁决
    5. 输出共识结论
    """

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.debate_log: list[str] = []

    def debate(self,
               question: str,
               conclusions: dict[str, str],
               evidence: dict[str, list[str]]) -> str:
        """
        组织辩论。

        Args:
            question: 原始问题
            conclusions: {agent_name: diagnosis}
            evidence: {agent_name: [evidence_list]}

        Returns:
            辩论后的共识结论
        """
        self.debate_log = []
        self.debate_log.append(f"辩论问题: {question}")
        self.debate_log.append(f"参与方: {list(conclusions.keys())}")

        # 1. 列出分歧点
        self.debate_log.append("\n--- 分歧点 ---")
        # 分歧点由各方结论的差异直接体现（确定性步骤，无需 LLM 分析）

        # 2. 收集各方观点
        for agent, conclusion in conclusions.items():
            self.debate_log.append(f"\n{agent} 的观点:\n{conclusion[:200]}")

        # 3. LLM 裁决：质量节点由主诊断模型承担（issue #104 收口确认，
        #    不接入独立裁判模型；此处即主 llm，非"简化实现"占位）
        consensus = self._judge(question, conclusions)
        self.debate_log.append(f"\n--- 裁决结果 ---\n{consensus}")

        return consensus

    def _judge(self, question: str, conclusions: dict[str, str]) -> str:
        """让 LLM 根据各方证据做出裁决"""
        view_points = "\n".join(
            f"{name}: {diag}" for name, diag in conclusions.items()
        )
        prompt = f"""作为运维专家，请分析以下多个 AI Agent 对同一问题的诊断结论，
判断哪个最准确，或综合给出更准确的结论。

问题：{question}

各 Agent 的诊断：
{view_points}

请给出最终判断，并说明理由："""

        response = self.llm.chat([
            {"role": "system", "content": "你是运维诊断专家，擅长综合分析多方面的信息。"},
            {"role": "user", "content": prompt},
        ], temperature=0.0)

        return response.get("content", "无法达成共识")

    def get_log(self) -> list[str]:
        return self.debate_log
