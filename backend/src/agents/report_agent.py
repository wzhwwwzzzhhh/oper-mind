"""Report Agent — 报告生成

将诊断结果转化为结构化报告，支持文字分析 + 图表数据。
"""

from src.core.public_projection import project_public_text, safe_request_topic


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
{safe_request_topic(query)}

"""
        # 各领域诊断结果
        for agent_name, diagnosis in diagnoses.items():
            safe_name = project_public_text(agent_name, limit=40)
            report += f"## {safe_name} 诊断\n{project_public_text(diagnosis)}\n\n"

        # 汇总根因
        report += "## 综合结论\n"
        report += self._summarize(diagnoses)

        # thinking 仅供内部运行态使用，公开报告不得展示思考链或工具参数。
        _ = thinking

        return report

    def _summarize(self, diagnoses: dict[str, str]) -> str:
        """汇总多 Agent 的诊断结论，给出综合根因"""
        parts = []
        for agent_name, diagnosis in diagnoses.items():
            # 提取前五行非空行作为摘要
            lines = [line for line in project_public_text(diagnosis).split("\n") if line.strip()]
            summary = "\n".join(lines[:5])
            parts.append(f"**{agent_name}**:\n{summary}")

        return "\n\n".join(parts)

    def get_thinking(self) -> list[str]:
        return self.thinking_log
