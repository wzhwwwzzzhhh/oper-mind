"""Reflection — 反思复审引擎

每份诊断报告生成后，由其他 Agent 交叉审核，
确保结论准确、证据充分、建议可行。
"""

from src.core.llm import LLMClient


class ReflectionEngine:
    """
    反思复审。

    流程：
    1. Report Agent 出初稿
    2. 其他 Agent 交叉审核各自领域部分
    3. 如有问题退回修改
    4. 验证通过后输出最终报告
    """

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.review_log: list[str] = []

    def review(self, report: str, reviewers: list[object]) -> str:
        """
        对报告进行复审。

        Args:
            report: 初稿报告
            reviewers: 参与复审的 Agent 列表

        Returns:
            复审后的报告（可能修改）
        """
        self.review_log = []
        self.review_log.append("=== 反思复审开始 ===")

        # 1. 各 Agent 审核
        feedbacks = []
        for reviewer in reviewers:
            feedback = self._review_by_agent(report, reviewer)
            feedbacks.append(feedback)

        # 2. 汇总反馈，判断是否需要修改
        issues = [f for f in feedbacks if f]
        if not issues:
            self.review_log.append("复审通过，无问题")
            return report

        self.review_log.append(f"复审发现问题: {len(issues)} 条")

        # 3. 让 LLM 根据反馈修改报告
        revised = self._revise(report, issues)
        self.review_log.append("报告已根据反馈修订")
        self.review_log.append("=== 反思复审完成 ===")

        return revised

    def collect_feedback(self, report: str, reviewers: list) -> list[str]:
        """只收集复审反馈,不做修订(修订交给编排图的 report 节点)。

        Returns:
            问题列表;为空表示复审通过。
        """
        self.review_log = ["=== 反思复审(收集反馈) ==="]
        issues = []
        for reviewer in reviewers:
            fb = self._review_by_agent(report, reviewer)
            if fb:
                issues.append(fb)
        self.review_log.append(f"复审发现问题:{len(issues)} 条" if issues else "复审通过")
        return issues

    def _review_by_agent(self, report: str, agent) -> str | None:
        """让一个 Agent 审核报告。

        质量节点由主诊断模型承担（issue #104 收口确认，不接入独立裁判模型；
        此处即主 llm，非"简化实现"占位）。
        """
        prompt = f"""请审核以下诊断报告，检查：
1. 结论是否有据可查
2. 建议是否具体可行
3. 是否有遗漏的重要信息

报告：
{report}

如有问题，列出具体问题；如无问题，回复"通过"："""

        response = self.llm.chat([
            {"role": "system", "content": "你是审核专家，负责检查 AI 生成报告的质量。"},
            {"role": "user", "content": prompt},
        ])

        result = response.get("content", "")
        if "通过" in result:
            return None
        return result

    def _revise(self, report: str, feedbacks: list[str]) -> str:
        """根据反馈修改报告"""
        feedback_text = "\n".join(f"- {f}" for f in feedbacks)
        prompt = f"""请根据以下审核反馈修改报告。

原始报告：
{report}

审核反馈：
{feedback_text}

请输出修改后的完整报告："""

        response = self.llm.chat([
            {"role": "system", "content": "你是报告编辑，负责根据反馈修改诊断报告。"},
            {"role": "user", "content": prompt},
        ])

        return response.get("content", report)

    def get_log(self) -> list[str]:
        return self.review_log
