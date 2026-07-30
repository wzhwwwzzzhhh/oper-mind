"""P4.1 订单慢查询调查结果的确定性组装器。"""

from __future__ import annotations

from src.application.contracts import DiagnosisExecutionResult, ResultAssembler
from src.domain.diagnosis import DiagnosisSeverity
from src.domain.records import DiagnosisResultData, DiagnosisRunData
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler


class DemoOrdersEvidenceResultAssembler(ResultAssembler):
    """把 P4.1 安全证据摘要转换为既有结构化 Result。"""

    def assemble(self, run: DiagnosisRunData, result: DiagnosisExecutionResult) -> DiagnosisResultData:
        """固定 recommendations/approval 边界，不生成任何修复或执行意图。"""
        investigation = result.evidence_investigation
        if investigation is None:
            raise ValueError("P4.1 执行结果缺少只读证据调查摘要。")
        return DiagnosisResultData(
            run_id=run.id,
            summary=investigation.summary,
            severity=investigation.severity,
            confidence=investigation.confidence,
            root_causes=[item.model_dump(mode="json") for item in investigation.root_causes],
            evidence=[item.model_dump(mode="json") for item in investigation.evidence],
            recommendations=[],
            risks=[item.model_dump(mode="json") for item in investigation.risks],
            requires_approval=False,
            agent_summary=[item.model_dump(mode="json") for item in investigation.agent_summary],
        )


class P4CompatibleResultAssembler(ResultAssembler):
    """在 P4.1 开启时仍保留非订单问题的 legacy 结果语义。"""

    def __init__(self) -> None:
        self._demo_assembler = DemoOrdersEvidenceResultAssembler()
        self._fallback_assembler = ConservativeResultAssembler()

    def assemble(self, run: DiagnosisRunData, result: DiagnosisExecutionResult) -> DiagnosisResultData:
        """有 P4.1 证据时走产品结果；未支持请求明确返回 MVP 范围说明。"""
        if result.evidence_investigation is not None:
            return self._demo_assembler.assemble(run, result)
        if result.strategy == "p4_unsupported_request":
            return DiagnosisResultData(
                run_id=run.id,
                summary="当前 MVP 只支持订单慢查询的只读调查；本次未连接数据库、日志或服务，也未执行任何操作。",
                severity=DiagnosisSeverity.INFO,
                confidence=0.0,
                root_causes=[],
                evidence=[],
                recommendations=[],
                risks=[],
                requires_approval=False,
                agent_summary=[],
            )
        return self._fallback_assembler.assemble(run, result)
