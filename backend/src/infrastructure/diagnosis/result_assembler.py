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
