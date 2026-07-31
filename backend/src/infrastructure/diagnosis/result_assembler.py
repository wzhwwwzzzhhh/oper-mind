"""P2 结构化诊断结果的保守组装器。"""

from __future__ import annotations

from src.application.contracts import DiagnosisExecutionResult, ResultAssembler
from src.domain.diagnosis import DiagnosisSeverity
from src.domain.records import DiagnosisResultData, DiagnosisRunData


class ConservativeResultAssembler(ResultAssembler):
    """不从 Markdown 或 Trace 推断事实的确定性保守结果组装器。"""

    def assemble(self, run: DiagnosisRunData, result: DiagnosisExecutionResult) -> DiagnosisResultData:
        """生成字段完整、低置信度、无未审查证据的安全结果。"""
        strategy_note = f"，执行策略为 {result.strategy}" if result.strategy else ""
        return DiagnosisResultData(
            run_id=run.id,
            summary=f"诊断执行已完成{strategy_note}；详细结构化结论待安全证据组装后提供。",
            severity=DiagnosisSeverity.INFO,
            confidence=0.0,
            root_causes=[],
            evidence=[],
            recommendations=[],
            risks=[],
            requires_approval=False,
            agent_summary=[],
        )


class KernelReportResultAssembler(ResultAssembler):
    """用多 Agent 内核的报告正文作为用户可读答复，结构化字段仍保守留空。

    P1 阶段：大脑已能产出面向用户的报告（=助手消息），但尚未接入受控工具，
    因此没有经过核实的结构化证据。此组装器把报告放进 summary/report_markdown，
    而 severity/confidence/证据/根因等一律保守留空，绝不从散文反推事实。
    """

    def assemble(self, run: DiagnosisRunData, result: DiagnosisExecutionResult) -> DiagnosisResultData:
        """把大脑报告作为答复，缺报告时回退到保守占位文案。"""
        report = result.report
        if report:
            summary = report
            report_markdown = report
        else:
            strategy_note = f"，执行策略为 {result.strategy}" if result.strategy else ""
            summary = f"诊断执行已完成{strategy_note}；本次未生成可展示的报告正文。"
            report_markdown = None
        return DiagnosisResultData(
            run_id=run.id,
            summary=summary,
            severity=DiagnosisSeverity.INFO,
            confidence=0.0,
            root_causes=[],
            evidence=[],
            recommendations=[],
            risks=[],
            requires_approval=False,
            agent_summary=[],
            report_markdown=report_markdown,
        )
