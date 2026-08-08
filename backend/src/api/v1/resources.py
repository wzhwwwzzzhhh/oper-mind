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
    HostDiskPartitionResource,
    HostMetricsResource,
    HostProcessResource,
    KnowledgeDocumentResource,
    KnowledgeSearchHitResource,
    MessageResource,
    ModelProviderResource,
    RunErrorResource,
    RunEventResource,
    ServiceActivityResource,
    ServiceDatabaseResource,
    ServiceInvestigationResource,
    ServiceResource,
    ServiceServerMetricsResource,
    ServiceSnapshotResource,
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
from src.domain.model_provider import ModelProviderData
from src.domain.records import DiagnosisResultData, DiagnosisRunData, MessageData, RunEventData, SessionData
from src.domain.services import ServiceActivityData, ServiceViewData
from src.domain.host_metrics import HostMetricsData
from src.domain.monitoring import MonitorHistoryData
from src.knowledge.reader import KnowledgeDocumentMeta, KnowledgeSearchHit
from src.core.tool_gateway import desensitize


def session_resource(value: SessionData) -> SessionResource:
    """把领域 Session 转为公开资源。"""
    return SessionResource(
        id=value.id,
        title=value.title,
        status=value.status.value,
        environment_id=value.environment_id,
        incident_id=value.incident_id,
        service_id=value.service_id,
        service_ids=list(value.service_ids),
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
        service_id=value.service_id,
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


def service_resource(value: ServiceViewData) -> ServiceResource:
    """将静态服务定义和有限快照映射为公开资源。"""
    definition = value.definition
    snapshot = value.snapshot
    return ServiceResource(
        id=definition.id,
        title=definition.title,
        kind=definition.kind,
        supported_investigations=[
            ServiceInvestigationResource(
                id=item.id,
                title=item.title,
                description=item.description,
                default_query=item.default_query,
            )
            for item in definition.supported_investigations
        ],
        action_boundary=definition.action_boundary,
        snapshot=ServiceSnapshotResource(
            observed_at=snapshot.observed_at,
            mode=snapshot.mode.value,
            availability=snapshot.availability.value,
            performance_signal=snapshot.performance_signal.value,
            server_metrics=ServiceServerMetricsResource(
                source_status=snapshot.server_metrics.source_status.value,
                window_size=snapshot.server_metrics.window_size,
                p50_ms=snapshot.server_metrics.p50_ms,
                p95_ms=snapshot.server_metrics.p95_ms,
                slow_query_count=snapshot.server_metrics.slow_query_count,
                timeout_count=snapshot.server_metrics.timeout_count,
                memory_bytes=snapshot.server_metrics.memory_bytes,
                client_connections=snapshot.server_metrics.client_connections,
                slowlog_count=snapshot.server_metrics.slowlog_count,
            ),
            database=ServiceDatabaseResource(
                source_status=snapshot.database.source_status.value,
                signal=snapshot.database.signal.value,
            ),
        ),
        host_metrics=host_metrics_resource(value.host_metrics),
    )


def host_metrics_resource(value: HostMetricsData) -> HostMetricsResource:
    """将主机指标领域模型映射为脱敏公开资源，标量保持 null 而非 0。"""
    return HostMetricsResource(
        mode=value.mode.value,
        source_status=value.source_status.value,
        observed_at=value.observed_at,
        cpu_percent=value.cpu_percent,
        cpu_count=value.cpu_count,
        load_avg_1m=value.load_avg_1m,
        memory_total_bytes=value.memory_total_bytes,
        memory_used_bytes=value.memory_used_bytes,
        memory_percent=value.memory_percent,
        disk_used_percent=value.disk_used_percent,
        disk_top_partitions=[
            HostDiskPartitionResource(
                mount=part.mount,
                percent=part.percent,
                used_bytes=part.used_bytes,
                total_bytes=part.total_bytes,
            )
            for part in value.disk_top_partitions
        ],
        network_connections=value.network_connections,
        network_established=value.network_established,
        network_time_wait=value.network_time_wait,
        abnormal_processes=[
            HostProcessResource(
                name=proc.name,
                pid=proc.pid,
                cpu_percent=proc.cpu_percent,
                memory_percent=proc.memory_percent,
            )
            for proc in value.abnormal_processes
        ],
    )


def service_activity_resource(value: ServiceActivityData) -> ServiceActivityResource:
    """将服务只读活动模型收敛为安全公开资源。"""
    return ServiceActivityResource(
        session_id=value.session_id,
        session_title=value.session_title,
        run_id=value.run_id,
        run_status=value.run_status,
        created_at=value.created_at,
        finished_at=value.finished_at,
        summary=value.summary,
        severity=value.severity,
        confidence=value.confidence,
        proposal_status=value.proposal_status,
        verification_status=value.verification_status,
    )


def monitor_history_resource(value: MonitorHistoryData) -> dict[str, object]:
    """将历史监控领域模型映射为已脱敏 API 字段。"""
    return {
        "service_id": value.service_id,
        "status": value.status.value,
        "source": value.source,
        "sample_interval_seconds": value.sample_interval_seconds,
        "retention_hours": value.retention_hours,
        "from": value.from_at,
        "to": value.to_at,
        "samples": [sample.model_dump() for sample in value.samples],
    }


def provider_resource(value: ModelProviderData) -> ModelProviderResource:
    """把领域 Provider 转为公开资源，绝不暴露密文或明文 Key。"""
    return ModelProviderResource(
        id=value.id,
        name=value.name,
        base_url=value.base_url,
        model=value.model,
        has_api_key=value.has_api_key,
        masked_tail=value.masked_tail,
        active_endpoint=value.active_endpoint.value if value.active_endpoint is not None else None,
        verify_status=value.verify_status.value,
        last_verified_at=value.last_verified_at,
        verify_error_code=value.verify_error_code,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def knowledge_document_resource(value: KnowledgeDocumentMeta) -> KnowledgeDocumentResource:
    """把 reader 文档清单条目映射为公开资源（relative_name → relative_path），标题脱敏兜底。"""
    return KnowledgeDocumentResource(
        title=desensitize(value.title),
        relative_path=value.relative_name,
    )


def knowledge_search_hit_resource(value: KnowledgeSearchHit) -> KnowledgeSearchHitResource:
    """把 reader 检索命中项映射为公开资源（relative_name → relative_path），标题与片段脱敏兜底。"""
    return KnowledgeSearchHitResource(
        title=desensitize(value.title),
        relative_path=value.relative_name,
        snippet_count=value.snippet_count,
        title_hit=value.title_hit,
        snippets=[desensitize(snippet) for snippet in value.snippets],
    )
