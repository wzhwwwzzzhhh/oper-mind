"""P2.4 v1 资源映射；所有读取结果先经公开 Pydantic 资源契约验证。"""

from __future__ import annotations

from src.api.v1.schemas import (
    ActionApprovalResource,
    ActionEventResource,
    ActionExecutionResource,
    ActionProposalResource,
    ActionVerificationResource,
    DiagnosisResultResource,
    DiagnosisRunResource,
    MessageResource,
    RunErrorResource,
    RunEventResource,
    SessionResource,
)
from src.domain.actions import (
    ActionApprovalData,
    ActionEventData,
    ActionExecutionData,
    ActionProposalDetail,
    ActionVerificationData,
)
from src.domain.diagnosis import RunStatus
from src.domain.records import DiagnosisResultData, DiagnosisRunData, MessageData, RunEventData, SessionData


def session_resource(value: SessionData) -> SessionResource:
    """把领域 Session 转为公开资源。"""
    return SessionResource(
        id=value.id,
        title=value.title,
        status=value.status.value,
        environment_id=value.environment_id,
        incident_id=value.incident_id,
        created_at=value.created_at,
        updated_at=value.updated_at,
        archived_at=value.archived_at,
    )


def message_resource(value: MessageData) -> MessageResource:
    """把领域 Message 转为公开资源。"""
    return MessageResource(
        id=value.id,
        session_id=value.session_id,
        run_id=value.run_id,
        role=value.role.value,
        content=value.content,
        created_at=value.created_at,
    )


def result_resource(value: DiagnosisResultData) -> DiagnosisResultResource:
    """读取结构化 Result 时执行公开 schema 校验，拒绝泄露未审查 JSON。"""
    return DiagnosisResultResource(
        id=value.id,
        run_id=value.run_id,
        summary=value.summary,
        severity=value.severity.value,
        confidence=value.confidence,
        root_causes=value.root_causes,
        evidence=value.evidence,
        impact=value.impact,
        recommendations=value.recommendations,
        risks=value.risks,
        requires_approval=value.requires_approval,
        agent_summary=value.agent_summary,
        report_markdown=value.report_markdown,
        created_at=value.created_at,
    )


def run_resource(value: DiagnosisRunData, result: DiagnosisResultData | None) -> DiagnosisRunResource:
    """把领域 Run 和可选 Result 转为符合终态规则的公开资源。"""
    error = None
    if value.status == RunStatus.FAILED:
        error = _safe_run_error(value.error_code, value.error_message)
    return DiagnosisRunResource(
        id=value.id,
        session_id=value.session_id,
        trace_id=value.trace_id,
        input_message_id=value.input_message_id,
        status=value.status.value,
        result=result_resource(result) if result is not None else None,
        error=error,
        created_at=value.created_at,
        started_at=value.started_at,
        finished_at=value.finished_at,
    )


def _safe_run_error(code: str | None, message: str | None) -> RunErrorResource:
    """为历史写入或未来导入提供纵深防御，绝不透传未经审查的错误文本。"""
    if code == "DIAGNOSIS_FAILED" and message == "诊断执行失败，请稍后重试":
        return RunErrorResource(code=code, message=message)
    return RunErrorResource(code="DIAGNOSIS_FAILED", message="诊断执行失败，请稍后重试")


def run_event_resource(value: RunEventData) -> RunEventResource:
    """把已提交领域事件映射为可重放公开事件。"""
    return RunEventResource(
        id=value.id,
        run_id=value.run_id,
        sequence=value.sequence,
        type=value.type.value,
        occurred_at=value.occurred_at,
        data=value.data,
    )


def action_proposal_resource(value: ActionProposalDetail) -> ActionProposalResource:
    """将不可编辑 Proposal 详情转为公开安全快照。"""
    proposal = value.proposal
    return ActionProposalResource(
        id=proposal.id, source_run_id=proposal.source_run_id, action_id=proposal.action_id,
        action_digest=proposal.action_digest, status=proposal.status.value, mode=proposal.mode,
        title=proposal.title, description=proposal.description, target=proposal.target,
        root_cause_id=proposal.root_cause_id, evidence_ids=proposal.evidence_ids,
        risk_summary=proposal.risk_summary, verification_plan=proposal.verification_plan,
        created_at=proposal.created_at, updated_at=proposal.updated_at, approved_at=proposal.approved_at,
        expires_at=proposal.expires_at, execution_started_at=proposal.execution_started_at,
        completed_at=proposal.completed_at, failure_code=proposal.failure_code,
        failure_message=proposal.failure_message,
        approval=action_approval_resource(value.approval) if value.approval is not None else None,
        execution=action_execution_resource(value.execution) if value.execution is not None else None,
        verification=action_verification_resource(value.verification) if value.verification is not None else None,
    )


def action_approval_resource(value: ActionApprovalData) -> ActionApprovalResource:
    """将审批记录映射为公开资源。"""
    return ActionApprovalResource(
        id=value.id, proposal_id=value.proposal_id, decision=value.decision.value, actor=value.actor,
        comment=value.comment, action_digest=value.action_digest, created_at=value.created_at,
    )


def action_execution_resource(value: ActionExecutionData) -> ActionExecutionResource:
    """将受控执行记录映射为公开资源。"""
    return ActionExecutionResource(
        id=value.id, proposal_id=value.proposal_id, mode=value.mode, status=value.status.value,
        precondition_summary=value.precondition_summary, action_summary=value.action_summary,
        failure_code=value.failure_code, failure_message=value.failure_message, created_at=value.created_at,
        started_at=value.started_at, finished_at=value.finished_at,
    )


def action_verification_resource(value: ActionVerificationData) -> ActionVerificationResource:
    """将 Verify 记录映射为公开安全资源。"""
    return ActionVerificationResource(
        id=value.id, execution_id=value.execution_id, status=value.status.value, mode=value.mode,
        summary=value.summary, facts=value.facts, created_at=value.created_at,
    )


def action_event_resource(value: ActionEventData) -> ActionEventResource:
    """将 action 审计事件映射为可轮询资源。"""
    return ActionEventResource(
        id=value.id, proposal_id=value.proposal_id, sequence=value.sequence, type=value.type.value,
        occurred_at=value.occurred_at, data=value.data,
    )
