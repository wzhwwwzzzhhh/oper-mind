"""Report Agent — 报告生成

将诊断结果转化为结构化报告，支持文字分析 + 图表数据。
"""


class ReportAgent:
    """
    报告生成 Agent。

    职责：
    1. 收集各 Agent 的诊断结论
    2. 格式化输出结构化报告
    3. 包含根因、依据、建议、预期效果、图表数据
    """

    def __init__(self):
        self.thinking_log: list[str] = []

    def generate(self,
                 query: str,
                 diagnoses: dict[str, str],
                 thinking: list[str] | None = None) -> str:
        """
        生成结构化诊断报告。

        Args:
            query: 原始用户问题
            diagnoses: {agent_name: diagnosis_text}
            thinking: 可选的思考过程

        Returns:
            格式化的诊断报告
        """
        self.thinking_log = []

        report = f"""# 运维诊断报告

## 问题描述
{query}

"""
        # 各领域诊断结果
        for agent_name, diagnosis in diagnoses.items():
            report += f"## {agent_name} 诊断\n{diagnosis}\n\n"

        # 汇总根因
        report += "## 综合结论\n"
        report += self._summarize(diagnoses)

        # 思考过程（可选）
        if thinking:
            report += "\n## 诊断链路\n"
            for step in thinking:
                report += f"- {step}\n"

        return report

    def _summarize(self, diagnoses: dict[str, str]) -> str:
        """汇总多 Agent 的诊断结论，给出综合根因"""
        parts = []
        for agent_name, diagnosis in diagnoses.items():
            # 提取前三行作为摘要
            lines = [l for l in diagnosis.split("\n") if l.strip()]
            summary = "\n".join(lines[:5])
            parts.append(f"**{agent_name}**:\n{summary}")

        return "\n\n".join(parts)

    def get_thinking(self) -> list[str]:
        return self.thinking_log
