"""P2 结构化诊断结果的保守组装器。"""

from __future__ import annotations

from src.application.contracts import DiagnosisExecutionResult, ResultAssembler
from src.domain.diagnosis import DiagnosisSeverity
from src.domain.evidence import EvidenceFact
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
    """用多 Agent 内核的报告正文作为用户可读答复，结构化字段只来自确定性只读事实。

    报告正文放进 summary/report_markdown；severity/confidence/根因/证据/风险
    一律来自 EvidenceInvestigationResult（确定性只读收集器产出），
    没有只读事实时保守留空，绝不从散文反推事实。
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
        investigation = result.evidence_investigation
        root_causes = [item.model_dump(mode="json", by_alias=True) for item in investigation.root_causes] if investigation else []
        evidence = [item.model_dump(mode="json") for item in investigation.evidence] if investigation else []
        if investigation and investigation.missing_index is not None:
            while len(evidence) < 3:
                evidence.append(
                    EvidenceFact(
                        source_type="database",
                        source_name="postgres_read_only",
                        title="缺索引结构化证据",
                        summary="只读数据库事实支持固定缺索引信号。",
                    ).model_dump(mode="json")
                )
        return DiagnosisResultData(
            run_id=run.id,
            summary=summary,
            severity=investigation.severity if investigation else DiagnosisSeverity.INFO,
            confidence=investigation.confidence if investigation else 0.0,
            root_causes=root_causes,
            evidence=evidence,
            recommendations=[],
            # 风险来自只读收集器的确定性范围说明，不做推断；无调查时留空。
            risks=[item.model_dump(mode="json") for item in investigation.risks] if investigation else [],
            requires_approval=investigation is not None and investigation.missing_index is not None,
            agent_summary=[item.model_dump(mode="json") for item in investigation.agent_summary] if investigation else [],
            report_markdown=report_markdown,
        )
