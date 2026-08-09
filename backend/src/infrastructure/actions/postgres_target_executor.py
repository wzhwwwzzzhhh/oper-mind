"""受控靶场 PostgreSQL 联合索引固定动作执行器。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.application.action_execution import (
    ActionExecutionAttempt,
    ActionPreconditionBlockedError,
    ActionVerificationFailedError,
    ActionVerificationOutcome,
    ControlledActionError,
)
from src.application.action_services import (
    COMPOUND_INDEX_ACTION_ID,
    COMPOUND_INDEX_VERIFICATION_PLAN,
    TARGET_COLUMNS,
    TARGET_INDEX_NAME,
    TARGET_SCHEMA,
    TARGET_SERVICE_ID,
    TARGET_TABLE,
)
from src.domain.actions import ActionProposalData, action_digest
from src.infrastructure.services.postgres_engine import create_read_write_postgres_engine

EngineFactory = Callable[[str], Engine]


class PostgresTargetActionExecutor:
    """只对静态 postgres-target 执行固定联合索引动作。"""

    def __init__(self, dsn: str | None, engine_factory: EngineFactory | None = None) -> None:
        self._dsn = dsn
        self._engine_factory = engine_factory or create_read_write_postgres_engine

    def execute(self, proposal: ActionProposalData) -> ActionExecutionAttempt:
        """复核固定提案和前置条件后提交唯一白名单 DDL。"""
        self._validate_proposal(proposal)
        if self._dsn is None:
            raise ActionPreconditionBlockedError()
        engine: Engine | None = None
        connection: Any | None = None
        write_engine: Engine | None = None
        write_connection: Any | None = None
        write_started = False
        try:
            engine = self._engine_factory(self._dsn)
            connection = engine.connect()
            table_exists = self._table_exists(connection)
            index_state = self._index_state(connection)
            if not table_exists or index_state is True or index_state == "invalid":
                raise ActionPreconditionBlockedError()
            connection.close()
            connection = None
            engine.dispose()
            engine = None
            write_engine = self._engine_factory(self._dsn)
            write_connection = write_engine.connect()
            write_connection = write_connection.execution_options(isolation_level="AUTOCOMMIT")
            write_started = True
            write_connection.execute(text(_CREATE_INDEX_SQL))
            return ActionExecutionAttempt(
                mode="target",
                precondition_summary="受控靶场固定目标表存在且索引不存在。",
                action_summary="受控靶场固定联合索引动作已提交。",
            )
        except ActionPreconditionBlockedError:
            raise
        except asyncio.CancelledError as error:
            if not write_started:
                raise ActionPreconditionBlockedError() from error
            raise ControlledActionError() from error
        except Exception as error:
            if not write_started:
                raise ActionPreconditionBlockedError() from error
            raise ControlledActionError() from error
        finally:
            if connection is not None:
                connection.close()
            if engine is not None:
                engine.dispose()
            if write_connection is not None:
                write_connection.close()
            if write_engine is not None:
                write_engine.dispose()

    def verify(self, proposal: ActionProposalData) -> ActionVerificationOutcome:
        """使用新建只读连接确认固定索引存在且可用。"""
        self._validate_proposal(proposal)
        if self._dsn is None:
            raise ActionVerificationFailedError()
        engine: Engine | None = None
        connection: Any | None = None
        try:
            engine = self._engine_factory(self._dsn)
            connection = engine.connect()
            connection.execute(text("SET TRANSACTION READ ONLY"))
            index_state = self._index_state(connection)
            plan_uses_index = _plan_uses_target_index(connection.execute(text(_VERIFY_INDEX_SQL)).mappings().all())
            if index_state is not True or not plan_uses_index:
                raise ActionVerificationFailedError()
            return ActionVerificationOutcome(
                mode="target",
                summary="受控靶场固定联合索引已存在且通过独立 Verify。",
                facts={"index_exists": True, "index_valid": True, "plan_uses_index": True},
            )
        except ActionVerificationFailedError:
            raise
        except asyncio.CancelledError as error:
            raise ActionVerificationFailedError() from error
        except Exception as error:
            raise ActionVerificationFailedError() from error
        finally:
            if connection is not None:
                connection.close()
            if engine is not None:
                engine.dispose()

    @staticmethod
    def _validate_proposal(proposal: ActionProposalData) -> None:
        """服务端重新校验不可编辑提案的固定模板和摘要。"""
        target = {
            "service_id": TARGET_SERVICE_ID,
            "schema": TARGET_SCHEMA,
            "table": TARGET_TABLE,
            "columns": ",".join(TARGET_COLUMNS),
            "index_name": TARGET_INDEX_NAME,
        }
        expected_digest = action_digest(
            action_id=COMPOUND_INDEX_ACTION_ID,
            source_run_id=proposal.source_run_id,
            root_cause_id=proposal.root_cause_id,
            evidence_ids=proposal.evidence_ids,
            target=target,
            verification_plan=COMPOUND_INDEX_VERIFICATION_PLAN,
        )
        if (
            proposal.mode != "target"
            or proposal.action_id != COMPOUND_INDEX_ACTION_ID
            or proposal.target != target
            or proposal.verification_plan != COMPOUND_INDEX_VERIFICATION_PLAN
            or proposal.action_digest != expected_digest
        ):
            raise ActionPreconditionBlockedError()

    @staticmethod
    def _table_exists(connection: Any) -> bool:
        # to_regclass 返回 regclass：PG 按 search_path 简化为 "orders"，只能判断非 None。
        return connection.execute(text("SELECT to_regclass('public.orders')")).scalar() is not None

    @staticmethod
    def _index_state(connection: Any) -> bool | str | None:
        valid = connection.execute(text(
            "SELECT EXISTS (SELECT 1 FROM pg_class index_ref "
            "JOIN pg_namespace index_ns ON index_ns.oid = index_ref.relnamespace "
            "JOIN pg_index ON pg_index.indexrelid = index_ref.oid "
            "JOIN pg_class table_ref ON table_ref.oid = pg_index.indrelid "
            "JOIN pg_namespace table_ns ON table_ns.oid = table_ref.relnamespace "
            "WHERE index_ns.nspname = 'public' AND table_ns.nspname = 'public' "
            "AND table_ref.relname = 'orders' AND index_ref.relname = 'idx_orders_customer_created_at' "
            "AND pg_index.indisvalid)"
        )).scalar()
        if valid is True:
            return True
        exists = connection.execute(text(
            "SELECT EXISTS (SELECT 1 FROM pg_class index_ref "
            "JOIN pg_namespace index_ns ON index_ns.oid = index_ref.relnamespace "
            "JOIN pg_index ON pg_index.indexrelid = index_ref.oid "
            "JOIN pg_class table_ref ON table_ref.oid = pg_index.indrelid "
            "JOIN pg_namespace table_ns ON table_ns.oid = table_ref.relnamespace "
            "WHERE index_ns.nspname = 'public' AND table_ns.nspname = 'public' "
            "AND table_ref.relname = 'orders' AND index_ref.relname = 'idx_orders_customer_created_at')"
        )).scalar()
        return "invalid" if exists is True else False


_CREATE_INDEX_SQL = "CREATE INDEX CONCURRENTLY idx_orders_customer_created_at ON public.orders (customer_id, created_at)"
_VERIFY_INDEX_SQL = "EXPLAIN (FORMAT JSON) SELECT customer_id, created_at FROM public.orders WHERE customer_id = 1 ORDER BY created_at"


def _plan_uses_target_index(rows: list[dict[str, object]]) -> bool:
    """从 EXPLAIN JSON 计划中确认目标索引被使用。"""
    for row in rows:
        payload = row.get("QUERY PLAN") or row.get("query plan")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                continue
        if _contains_index_scan(payload):
            return True
    return False


def _contains_index_scan(value: object) -> bool:
    """递归查找固定索引扫描节点，不返回原始执行计划。"""
    if isinstance(value, dict):
        if value.get("Index Name") == TARGET_INDEX_NAME:
            return True
        return any(_contains_index_scan(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_index_scan(item) for item in value)
    return False
