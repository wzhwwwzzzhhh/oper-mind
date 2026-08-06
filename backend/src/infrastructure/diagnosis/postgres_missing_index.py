"""受控靶场 PostgreSQL 缺索引只读事实收集器。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.application.action_services import TARGET_COLUMNS, TARGET_INDEX_NAME, TARGET_SCHEMA, TARGET_SERVICE_ID, TARGET_TABLE
from src.domain.diagnosis import DiagnosisSeverity
from src.domain.evidence import EvidenceFact, EvidenceInvestigationResult, MissingIndexSignal, RootCauseFact
from src.infrastructure.services.postgres_engine import create_read_only_postgres_engine


class PostgresMissingIndexCollector:
    """只读取固定靶场对象，返回可触发动作的结构化事实。"""

    def __init__(self, dsn: str | None) -> None:
        self._dsn = dsn

    def collect(self, service_id: str | None, query: str) -> EvidenceInvestigationResult | None:
        """确认固定对象缺索引且执行计划为 Seq Scan；失败时无信号。"""
        if service_id != TARGET_SERVICE_ID or self._dsn is None or not _is_index_investigation(query):
            return None
        engine: Engine | None = None
        connection: Any | None = None
        try:
            engine = create_read_only_postgres_engine(self._dsn)
            connection = engine.connect()
            connection.execute(text("SET TRANSACTION READ ONLY"))
            if connection.execute(text("SELECT to_regclass('public.orders')")).scalar() != "public.orders":
                return None
            index_exists = connection.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_class index_ref "
                    "JOIN pg_index ON pg_index.indexrelid = index_ref.oid "
                    "JOIN pg_class table_ref ON table_ref.oid = pg_index.indrelid "
                    "JOIN pg_namespace index_ns ON index_ns.oid = index_ref.relnamespace "
                    "JOIN pg_namespace table_ns ON table_ns.oid = table_ref.relnamespace "
                    "WHERE index_ns.nspname = 'public' AND table_ns.nspname = 'public' "
                    "AND table_ref.relname = 'orders' AND index_ref.relname = 'idx_orders_customer_created_at' "
                    "AND pg_index.indisvalid)"
                )
            ).scalar() is True
            if index_exists:
                return None
            plan_rows = connection.execute(
                text(
                    "EXPLAIN (FORMAT JSON) SELECT customer_id, created_at FROM public.orders "
                    "WHERE customer_id = 1 ORDER BY created_at"
                )
            ).mappings().all()
            if not _contains_seq_scan(plan_rows):
                return None
            signal = MissingIndexSignal(
                service_id=TARGET_SERVICE_ID,
                schema_name=TARGET_SCHEMA,
                table=TARGET_TABLE,
                columns=TARGET_COLUMNS,
                index_name=TARGET_INDEX_NAME,
            )
            evidence = [
                EvidenceFact(source_type="database", source_name="postgres_read_only", title="目标表存在", summary="只读事实确认受控靶场固定目标表存在。"),
                EvidenceFact(source_type="database", source_name="postgres_read_only", title="固定联合索引缺失", summary="只读系统目录确认固定联合索引当前不存在。"),
                EvidenceFact(source_type="database", source_name="postgres_read_only", title="顺序扫描信号", summary="只读执行计划确认固定查询出现顺序扫描。"),
            ]
            root_cause = RootCauseFact(
                title="固定联合索引缺失",
                summary="只读事实同时确认目标索引缺失与顺序扫描。",
                confidence=1.0,
                evidence_ids=[item.id for item in evidence],
                missing_index=signal,
            )
            return EvidenceInvestigationResult(
                summary="只读诊断确认固定目标存在缺索引与顺序扫描信号。",
                severity=DiagnosisSeverity.HIGH,
                confidence=1.0,
                root_causes=[root_cause],
                evidence=evidence,
                missing_index=signal,
            )
        except Exception:
            return None
        finally:
            if connection is not None:
                connection.close()
            if engine is not None:
                engine.dispose()


def _contains_seq_scan(rows: list[dict[str, Any]]) -> bool:
    """仅从 EXPLAIN 结构化结果判断是否存在顺序扫描。"""
    for row in rows:
        payload = row.get("QUERY PLAN") or row.get("query plan")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        if _walk_plan(payload):
            return True
    return False


def _is_index_investigation(query: str) -> bool:
    """仅对明确的慢查询诊断意图运行固定只读收集。"""
    lowered = query.lower()
    if any(keyword in lowered for keyword in ("建索引", "创建索引", "执行索引", "create index")):
        return False
    evidence_intent = any(keyword in lowered for keyword in ("慢查询", "慢sql", "seq scan", "explain"))
    investigation_intent = any(keyword in lowered for keyword in ("排查", "调查", "诊断", "定位", "分析"))
    return evidence_intent and investigation_intent


def _walk_plan(value: object) -> bool:
    """递归检查计划节点类型，不把原始计划带出收集器。"""
    if isinstance(value, dict):
        if value.get("Node Type") == "Seq Scan":
            return True
        return any(_walk_plan(item) for item in value.values())
    if isinstance(value, list):
        return any(_walk_plan(item) for item in value)
    return False
