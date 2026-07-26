"""P2.4 v1 资源映射；所有读取结果先经公开 Pydantic 资源契约验证。"""

from __future__ import annotations

from src.api.v1.schemas import (
    DiagnosisResultResource,
    DiagnosisRunResource,
    MessageResource,
    RunErrorResource,
    RunEventResource,
    SessionResource,
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
