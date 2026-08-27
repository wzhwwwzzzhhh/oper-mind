"""受控动作的代码内白名单模板与确定性事实匹配。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import JsonValue

from src.domain.records import DiagnosisResultData

COMPOUND_INDEX_ACTION_ID = "postgres.orders_compound_index_rebuild.v1"
TARGET_SERVICE_ID = "postgres-target"
TARGET_SCHEMA = "public"
TARGET_TABLE = "orders"
TARGET_COLUMNS = ("customer_id", "created_at")
TARGET_INDEX_NAME = "idx_orders_customer_created_at"
COMPOUND_INDEX_VERIFICATION_PLAN = [
    "确认受控靶场目标表存在",
    "确认固定联合索引存在且有效",
    "只读执行计划确认固定索引可用",
]

_REQUIRED_EVIDENCE_TITLES = (
    "目标表存在",
    "固定联合索引缺失",
    "顺序扫描信号",
)


@dataclass(frozen=True)
class ControlledActionTemplate:
    """不会从配置或模型动态扩展的固定动作模板。"""

    action_id: str
    recommendation_title: str
    recommendation_description: str
    recommendation_priority: str
    recommendation_risk_level: str
    impact_summary: str
    impact_scope: str


@dataclass(frozen=True)
class MatchedControlledActionFacts:
    """通过完整白名单匹配的根因与只读证据引用。"""

    root_cause_id: UUID
    evidence_ids: tuple[UUID, ...]


COMPOUND_INDEX_TEMPLATE = ControlledActionTemplate(
    action_id=COMPOUND_INDEX_ACTION_ID,
    recommendation_title="评估受控靶场联合索引重建",
    recommendation_description=(
        "来源：受控动作模板 postgres.orders_compound_index_rebuild.v1。"
        "该建议只说明存在可审批的固定动作，不会自动生成审批决定或执行变更。"
    ),
    recommendation_priority="p1",
    recommendation_risk_level="medium",
    impact_summary=(
        "只读事实确认受控靶场固定数据库对象存在缺索引与顺序扫描信号；"
        "本次未采集业务调用方或终端用户影响。"
    ),
    impact_scope="受控靶场固定数据库对象（不代表业务影响范围）",
)


def recommendation_id(action_id: str) -> UUID:
    """从公开白名单动作 id 派生稳定的建议模板 UUID。"""
    return uuid5(NAMESPACE_URL, f"opermind:controlled-action-recommendation:{action_id}")


def match_compound_index_result(result: DiagnosisResultData) -> MatchedControlledActionFacts | None:
    """仅在 signal、根因和三类真实只读证据完整闭合时命中模板。"""
    evidence_by_id = {
        item.get("id"): item
        for item in result.evidence
        if isinstance(item.get("id"), str)
    }
    for root_cause in result.root_causes:
        if not _matches_target_signal(root_cause.get("missing_index")):
            continue
        root_cause_id = _parse_uuid(root_cause.get("id"))
        raw_evidence_ids = root_cause.get("evidence_ids")
        if root_cause_id is None or not isinstance(raw_evidence_ids, list):
            continue
        referenced: dict[str, UUID] = {}
        invalid_reference = False
        for raw_id in raw_evidence_ids:
            parsed_id = _parse_uuid(raw_id)
            evidence = evidence_by_id.get(raw_id) if isinstance(raw_id, str) else None
            if parsed_id is None or evidence is None:
                invalid_reference = True
                break
            if (
                evidence.get("source_type") == "database"
                and evidence.get("source_name") == "postgres_read_only"
                and evidence.get("title") in _REQUIRED_EVIDENCE_TITLES
            ):
                referenced[str(evidence["title"])] = parsed_id
        if invalid_reference or any(title not in referenced for title in _REQUIRED_EVIDENCE_TITLES):
            continue
        return MatchedControlledActionFacts(
            root_cause_id=root_cause_id,
            evidence_ids=tuple(referenced[title] for title in _REQUIRED_EVIDENCE_TITLES),
        )
    return None


def _matches_target_signal(value: JsonValue | None) -> bool:
    """严格匹配唯一已确认动作模板的固定目标。"""
    return isinstance(value, dict) and value == {
        "service_id": TARGET_SERVICE_ID,
        "schema": TARGET_SCHEMA,
        "table": TARGET_TABLE,
        "columns": list(TARGET_COLUMNS),
        "index_name": TARGET_INDEX_NAME,
    }


def _parse_uuid(value: JsonValue | None) -> UUID | None:
    """安全读取公开结构中的 UUID 字符串。"""
    if not isinstance(value, str):
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
