"""P4.1 三类只读证据 Collector 与确定性结果规则。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Generic, TypeVar

from src.domain.diagnosis import DiagnosisSeverity
from src.domain.evidence import (
    AgentInvestigationSummary,
    EvidenceFact,
    EvidenceInvestigationResult,
    RiskFact,
    RootCauseFact,
)
from src.infrastructure.diagnosis.demo_orders.models import (
    DatabaseEvidenceSnapshot,
    LogEvidenceSnapshot,
    ServerEvidenceSnapshot,
)
from src.infrastructure.diagnosis.demo_orders.postgres_reader import DemoOrdersSourceError


SnapshotT = TypeVar("SnapshotT", DatabaseEvidenceSnapshot, LogEvidenceSnapshot, ServerEvidenceSnapshot)


@dataclass(frozen=True)
class CollectorOutcome(Generic[SnapshotT]):
    """一个调查角色的脱敏采集终态。"""

    role: str
    snapshot: SnapshotT | None
    duration_ms: int

    @property
    def completed(self) -> bool:
        """Collector 是否成功产生了可用快照。"""
        return self.snapshot is not None


class SnapshotCollector(Generic[SnapshotT]):
    """把一个固定只读 reader 约束为可安全失败的调查 Collector。"""

    def __init__(self, role: str, reader: Callable[[], SnapshotT]) -> None:
        self.role = role
        self._reader = reader

    def collect(self) -> CollectorOutcome[SnapshotT]:
        """执行一次只读读取，只向编排器返回脱敏成功/失败状态。"""
        started = perf_counter()
        try:
            snapshot = self._reader()
        except (DemoOrdersSourceError, OSError, ValueError):
            snapshot = None
        duration_ms = max(0, round((perf_counter() - started) * 1000))
        return CollectorOutcome(role=self.role, snapshot=snapshot, duration_ms=duration_ms)


def build_evidence_investigation_result(
    database: CollectorOutcome[DatabaseEvidenceSnapshot],
    logs: CollectorOutcome[LogEvidenceSnapshot],
    server: CollectorOutcome[ServerEvidenceSnapshot],
) -> EvidenceInvestigationResult:
    """根据 P4.1 唯一根因规则生成结构化、可公开的调查结论。"""
    outcomes = (database, logs, server)
    if not any(outcome.completed for outcome in outcomes):
        raise DemoOrdersSourceError("全部只读证据源不可用")

    evidence = _evidence_facts(database, logs, server)
    agent_summary = _agent_summaries(database, logs, server)
    database_snapshot = database.snapshot
    logs_support = _logs_support_slow_query(logs.snapshot)
    server_support = _server_support_slow_query(server.snapshot)

    if database_snapshot is not None and _database_confirms_missing_index(database_snapshot):
        supporting_evidence_ids = [fact.id for fact in evidence if fact.source_type == "database"]
        supporting_evidence_ids.extend(
            fact.id
            for fact in evidence
            if fact.source_type in {"log", "metric"} and _source_supports_anomaly(fact, logs_support, server_support)
        )
        if logs_support and server_support:
            return EvidenceInvestigationResult(
                summary="订单慢查询已确认：目标索引缺失，执行计划出现顺序扫描，日志和服务指标均支持延迟异常。",
                severity=DiagnosisSeverity.HIGH,
                confidence=0.95,
                root_causes=[
                    RootCauseFact(
                        title="订单查询缺少复合索引",
                        summary="固定订单查询在目标表上出现顺序扫描，且目标复合索引不存在；日志与服务指标同时出现慢查询异常。",
                        confidence=0.95,
                        evidence_ids=supporting_evidence_ids,
                    )
                ],
                evidence=evidence,
                risks=_investigation_scope_risks(outcomes),
                agent_summary=agent_summary,
            )
        return EvidenceInvestigationResult(
            summary="订单慢查询存在高风险线索：数据库显示目标索引缺失且执行计划出现顺序扫描，但其他证据源未能完整支持延迟异常。",
            severity=DiagnosisSeverity.HIGH,
            confidence=0.70,
            root_causes=[
                RootCauseFact(
                    title="订单查询缺少复合索引（待补充交叉证据）",
                    summary="数据库已显示目标索引缺失和顺序扫描；需要补充日志或服务指标后再确认影响程度。",
                    confidence=0.70,
                    evidence_ids=supporting_evidence_ids,
                )
            ],
            evidence=evidence,
            risks=[
                RiskFact(
                    level="medium",
                    summary="交叉证据不完整，本次仅能确认高风险线索，不能据此执行任何修复动作。",
                    mitigation="恢复日志和服务只读证据后重新调查。",
                ),
                *_investigation_scope_risks(outcomes),
            ],
            agent_summary=agent_summary,
        )

    return EvidenceInvestigationResult(
        summary="本次只读调查未确认订单慢查询由目标索引缺失导致；未生成修复提案或执行动作。",
        severity=DiagnosisSeverity.INFO,
        confidence=0.0,
        root_causes=[],
        evidence=evidence,
        risks=[
            RiskFact(
                level="medium",
                summary="未满足“索引缺失且顺序扫描”的确认规则，不能将慢查询归因于缺失索引。",
                mitigation="保持只读调查，补充可用证据后重新运行。",
            ),
            *_investigation_scope_risks(outcomes),
        ],
        agent_summary=agent_summary,
    )


def _database_confirms_missing_index(snapshot: DatabaseEvidenceSnapshot) -> bool:
    """执行唯一允许的数据库根因前置条件判断。"""
    return snapshot.target_database_confirmed and not snapshot.target_index_exists and snapshot.plan_uses_seq_scan


def _logs_support_slow_query(snapshot: LogEvidenceSnapshot | None) -> bool:
    """日志仅以聚合慢查询/超时计数支持异常。"""
    return snapshot is not None and (snapshot.slow_query_count > 0 or snapshot.timeout_count > 0)


def _server_support_slow_query(snapshot: ServerEvidenceSnapshot | None) -> bool:
    """服务仅以聚合异常计数或超过阈值的 p95 支持异常。"""
    if snapshot is None:
        return False
    if snapshot.slow_query_count > 0 or snapshot.timeout_count > 0:
        return True
    return (
        snapshot.p95_ms is not None
        and snapshot.slow_query_threshold_ms is not None
        and snapshot.p95_ms >= snapshot.slow_query_threshold_ms
    )


def _source_supports_anomaly(fact: EvidenceFact, logs_support: bool, server_support: bool) -> bool:
    """保证根因引用的证据确实参与了异常支持判断。"""
    return (fact.source_type == "log" and logs_support) or (fact.source_type == "metric" and server_support)


def _evidence_facts(
    database: CollectorOutcome[DatabaseEvidenceSnapshot],
    logs: CollectorOutcome[LogEvidenceSnapshot],
    server: CollectorOutcome[ServerEvidenceSnapshot],
) -> list[EvidenceFact]:
    """把成功快照转换为公开 schema 接受的标量事实。"""
    facts: list[EvidenceFact] = []
    if database.snapshot is not None:
        snapshot = database.snapshot
        facts.append(
            EvidenceFact(
                source_type="database",
                source_name="orders-postgresql",
                title="订单表索引与执行计划",
                summary=(
                    "目标复合索引不存在，固定订单查询计划出现顺序扫描。"
                    if not snapshot.target_index_exists and snapshot.plan_uses_seq_scan
                    else "已读取目标索引状态和固定订单查询的访问路径。"
                ),
                locator="opermind_demo.orders",
                observed_at=snapshot.observed_at,
                attributes={
                    "target_database_confirmed": snapshot.target_database_confirmed,
                    "target_index_exists": snapshot.target_index_exists,
                    "plan_uses_seq_scan": snapshot.plan_uses_seq_scan,
                    "plan_uses_target_index": snapshot.plan_uses_target_index,
                },
            )
        )
    if logs.snapshot is not None:
        snapshot = logs.snapshot
        facts.append(
            EvidenceFact(
                source_type="log",
                source_name="order-service-log",
                title="订单服务慢查询聚合日志",
                summary="已读取有限日志窗口的慢查询与超时聚合计数。",
                locator="order-service.jsonl（聚合窗口）",
                observed_at=snapshot.observed_at,
                attributes={
                    "matched_query_count": snapshot.matched_query_count,
                    "slow_query_count": snapshot.slow_query_count,
                    "timeout_count": snapshot.timeout_count,
                },
            )
        )
    if server.snapshot is not None:
        snapshot = server.snapshot
        facts.append(
            EvidenceFact(
                source_type="metric",
                source_name="order-service",
                title="订单服务健康与聚合指标",
                summary="已读取健康状态和有限性能指标，未调用会改变靶场状态的探测接口。",
                locator="订单服务 health 与诊断指标",
                observed_at=snapshot.observed_at,
                attributes={
                    "service_healthy": snapshot.service_healthy,
                    "window_size": snapshot.window_size,
                    "p50_ms": snapshot.p50_ms,
                    "p95_ms": snapshot.p95_ms,
                    "slow_query_count": snapshot.slow_query_count,
                    "timeout_count": snapshot.timeout_count,
                    "slow_query_threshold_ms": snapshot.slow_query_threshold_ms,
                },
            )
        )
    return facts


def _agent_summaries(
    database: CollectorOutcome[DatabaseEvidenceSnapshot],
    logs: CollectorOutcome[LogEvidenceSnapshot],
    server: CollectorOutcome[ServerEvidenceSnapshot],
) -> list[AgentInvestigationSummary]:
    """只生成角色级过程摘要，不输出思维链或读取细节。"""
    return [
        _agent_summary(database, "数据库"),
        _agent_summary(logs, "日志"),
        _agent_summary(server, "服务"),
    ]


def _agent_summary(outcome: CollectorOutcome[SnapshotT], display_name: str) -> AgentInvestigationSummary:
    """转换单个 Collector 的安全完成状态。"""
    if outcome.completed:
        return AgentInvestigationSummary(
            agent=outcome.role,
            status="completed",
            summary=f"{display_name}只读证据已收集。",
            duration_ms=outcome.duration_ms,
        )
    return AgentInvestigationSummary(
        agent=outcome.role,
        status="failed",
        summary=f"{display_name}只读证据暂不可用，未暴露内部错误详情。",
        duration_ms=outcome.duration_ms,
    )


def _investigation_scope_risks(outcomes: tuple[CollectorOutcome[object], ...]) -> list[RiskFact]:
    """对部分源失败显式提示调查范围，避免把缺失数据伪造成正常。"""
    unavailable_roles = [outcome.role for outcome in outcomes if not outcome.completed]
    if not unavailable_roles:
        return [
            RiskFact(
                level="low",
                summary="证据来自本地受控靶场，仅用于当前订单慢查询演示场景。",
                mitigation="接入真实服务前需单独完成数据源、权限与审批设计。",
            )
        ]
    return [
        RiskFact(
            level="medium",
            summary="部分只读证据源不可用，结论已按可用证据降级。",
            mitigation="恢复不可用证据源后重新调查。",
        )
    ]
