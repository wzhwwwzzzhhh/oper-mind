"""P4.2 订单慢查询固定索引的独立白名单执行器与 Verify 适配器。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections import deque
from typing import Protocol
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from src.domain.actions import (
    ORDERS_INDEX_REPAIR_ACTION_ID,
    ActionMode,
    ActionProposalData,
    action_digest,
)
from src.infrastructure.diagnosis.demo_orders.settings import (
    TARGET_DATABASE,
    TARGET_INDEX,
    TARGET_SCHEMA,
    TARGET_TABLE,
    DemoOrdersEvidenceSettings,
    EvidenceMode,
)

CREATE_ORDERS_INDEX_SQL = """
CREATE INDEX idx_orders_user_created
ON opermind_demo.orders (user_id, created_at)
"""
FIXED_EXPLAIN_SQL = """
EXPLAIN (FORMAT JSON)
SELECT id, order_no, status, total_amount, created_at
FROM opermind_demo.orders
WHERE user_id = %s
  AND created_at >= %s
  AND created_at < %s
ORDER BY created_at DESC
LIMIT 100
"""
FIXED_EXPLAIN_PARAMETERS = (42, "2025-01-01 00:00:00", "2026-01-01 00:00:00")


class ControlledActionError(Exception):
    """执行器向应用层报告的安全失败，不携带驱动或网络细节。"""

    code = "ACTION_EXECUTION_FAILED"
    message = "固定修复执行失败，未暴露内部错误详情。"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)


class ActionPreconditionBlockedError(ControlledActionError):
    """执行前重新校验未通过，保证不发送 DDL。"""

    code = "ACTION_PRECONDITION_BLOCKED"
    message = "执行前置条件未满足，系统未执行固定修复。"


class ActionVerificationFailedError(ControlledActionError):
    """DDL 后独立 Verify 未通过。"""

    code = "ACTION_VERIFICATION_FAILED"
    message = "验证未通过；固定索引可能已提交，系统未自动回滚。"


@dataclass(frozen=True)
class ActionExecutionAttempt:
    """执行器返回给应用层的最小语义化执行结果。"""

    mode: ActionMode
    precondition_summary: str
    action_summary: str


@dataclass(frozen=True)
class ActionVerificationOutcome:
    """不包含 request id、原始日志或 SQL 的 Verify 摘要。"""

    mode: ActionMode
    summary: str
    facts: dict[str, bool | int | str]


class OrdersIndexRepairExecutor(Protocol):
    """唯一固定 action 的执行与独立 Verify 端口。"""

    def execute(self, proposal: ActionProposalData) -> ActionExecutionAttempt:
        """重新检查前置条件后执行代码内固定 DDL。"""

    def verify(self, proposal: ActionProposalData) -> ActionVerificationOutcome:
        """执行独立只读 Verify，不进行回滚。"""


class MockOrdersIndexRepairExecutor:
    """确定性 mock，不建立 PostgreSQL 或 HTTP 连接。"""

    def execute(self, proposal: ActionProposalData) -> ActionExecutionAttempt:
        _validate_fixed_proposal(proposal, "mock")
        return ActionExecutionAttempt(
            mode="mock",
            precondition_summary="模拟模式已确认固定靶场前置条件。",
            action_summary="模拟模式已完成固定联合索引重建；未执行真实 DDL。",
        )

    def verify(self, proposal: ActionProposalData) -> ActionVerificationOutcome:
        _validate_fixed_proposal(proposal, "mock")
        return ActionVerificationOutcome(
            mode="mock",
            summary="模拟 Verify 已通过；未连接真实数据库、服务或日志。",
            facts={
                "target_database_confirmed": True,
                "target_index_exists": True,
                "plan_uses_target_index": True,
                "probe_count": 3,
                "probe_slow_query_count": 0,
                "probe_timeout_count": 0,
                "matched_log_count": 3,
                "matched_log_slow_query_count": 0,
                "matched_log_timeout_count": 0,
            },
        )


@dataclass(frozen=True)
class ProbeResult:
    """只在 Verify 内存中保留的单次固定服务探测。"""

    request_id: str
    slow_query: bool
    timeout: bool


class PostgresOrdersIndexRepairExecutor:
    """只操作固定本地靶场的独立受控 PostgreSQL 执行器。"""

    def __init__(self, settings: DemoOrdersEvidenceSettings) -> None:
        if settings.mode is not EvidenceMode.TARGET:
            raise ValueError("target 执行器只能使用 target 模式靶场配置。")
        self._settings = settings

    def execute(self, proposal: ActionProposalData) -> ActionExecutionAttempt:
        """先独立重校验，再执行唯一常量 DDL，任何失败均不重试。"""
        _validate_fixed_proposal(proposal, "target")
        self._assert_preconditions()
        try:
            with self._connection() as connection:
                with connection.cursor() as cursor:
                    self._assert_current_database(cursor)
                    cursor.execute(CREATE_ORDERS_INDEX_SQL)
                connection.commit()
        except ActionPreconditionBlockedError:
            raise
        except (psycopg.Error, OSError, ValueError) as error:
            raise ControlledActionError() from error
        return ActionExecutionAttempt(
            mode="target",
            precondition_summary="已确认目标索引缺失且固定计划仍为顺序扫描。",
            action_summary="已提交固定订单查询联合索引重建。",
        )

    def verify(self, proposal: ActionProposalData) -> ActionVerificationOutcome:
        """使用独立连接、固定三次探测和限定日志匹配完成 Verify。"""
        _validate_fixed_proposal(proposal, "target")
        try:
            index_exists, plan_uses_target_index = self._read_post_repair_database_facts()
            probe_results = [self._request_probe() for _ in range(3)]
            request_ids = {item.request_id for item in probe_results}
            log_facts = _matching_log_facts(self._settings.log_file, self._settings.log_line_limit, request_ids)
        except (psycopg.Error, OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise ActionVerificationFailedError() from error
        probe_slow_query_count = sum(1 for item in probe_results if item.slow_query)
        probe_timeout_count = sum(1 for item in probe_results if item.timeout)
        facts: dict[str, bool | int | str] = {
            "target_database_confirmed": True,
            "target_index_exists": index_exists,
            "plan_uses_target_index": plan_uses_target_index,
            "probe_count": 3,
            "probe_slow_query_count": probe_slow_query_count,
            "probe_timeout_count": probe_timeout_count,
            **log_facts,
        }
        passed = (
            index_exists
            and plan_uses_target_index
            and probe_slow_query_count == 0
            and probe_timeout_count == 0
            and log_facts["matched_log_count"] == 3
            and log_facts["matched_log_slow_query_count"] == 0
            and log_facts["matched_log_timeout_count"] == 0
        )
        if not passed:
            raise ActionVerificationFailedError()
        return ActionVerificationOutcome(
            mode="target",
            summary="Verify 已通过：目标索引和固定计划正常，3 次固定探测及匹配日志均无慢查询或超时。",
            facts=facts,
        )

    def _assert_preconditions(self) -> None:
        """在任何 DDL 前执行固定目标、索引和计划检查。"""
        try:
            with self._connection() as connection:
                with connection.cursor() as cursor:
                    self._assert_current_database(cursor)
                    cursor.execute("SELECT to_regclass('opermind_demo.orders') AS target_table")
                    table_row = cursor.fetchone()
                    if not isinstance(table_row, dict) or table_row.get("target_table") != "opermind_demo.orders":
                        raise ActionPreconditionBlockedError()
                    cursor.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM pg_indexes
                            WHERE schemaname = %s AND tablename = %s AND indexname = %s
                        ) AS target_index_exists
                        """,
                        (TARGET_SCHEMA, TARGET_TABLE, TARGET_INDEX),
                    )
                    index_row = cursor.fetchone()
                    if not isinstance(index_row, dict) or index_row.get("target_index_exists") is not False:
                        raise ActionPreconditionBlockedError()
                    cursor.execute(FIXED_EXPLAIN_SQL, FIXED_EXPLAIN_PARAMETERS)
                    plan_row = cursor.fetchone()
                    if not isinstance(plan_row, dict) or not _plan_uses_seq_scan(plan_row.get("QUERY PLAN")):
                        raise ActionPreconditionBlockedError()
        except ActionPreconditionBlockedError:
            raise
        except (psycopg.Error, OSError, ValueError) as error:
            raise ControlledActionError() from error

    def _read_post_repair_database_facts(self) -> tuple[bool, bool]:
        with self._connection() as connection:
            with connection.cursor() as cursor:
                self._assert_current_database(cursor)
                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM pg_indexes
                        WHERE schemaname = %s AND tablename = %s AND indexname = %s
                    ) AS target_index_exists
                    """,
                    (TARGET_SCHEMA, TARGET_TABLE, TARGET_INDEX),
                )
                index_row = cursor.fetchone()
                cursor.execute(FIXED_EXPLAIN_SQL, FIXED_EXPLAIN_PARAMETERS)
                plan_row = cursor.fetchone()
        if not isinstance(index_row, dict) or not isinstance(plan_row, dict):
            raise ActionVerificationFailedError()
        return bool(index_row.get("target_index_exists")), _plan_uses_target_index(plan_row.get("QUERY PLAN"))

    def _request_probe(self) -> ProbeResult:
        request = urllib.request.Request(
            f"{self._settings.service_base_url.rstrip('/')}/orders/diagnostic-probe", method="GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=self._settings.connection_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, UnicodeDecodeError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise ActionVerificationFailedError() from error
        if not isinstance(payload, dict):
            raise ActionVerificationFailedError()
        request_id = payload.get("request_id")
        slow_query = payload.get("slow_query")
        timeout = payload.get("timeout")
        if not isinstance(request_id, str) or not request_id or not isinstance(slow_query, bool) or not isinstance(timeout, bool):
            raise ActionVerificationFailedError()
        return ProbeResult(request_id=request_id, slow_query=slow_query, timeout=timeout)

    def _connection(self):
        password = self._settings.database_password
        if self._settings.database_user is None or password is None:
            raise ControlledActionError()
        return psycopg.connect(
            host=self._settings.database_host,
            port=self._settings.database_port,
            dbname=self._settings.database_name,
            user=self._settings.database_user,
            password=password.get_secret_value(),
            connect_timeout=self._settings.connection_timeout_seconds,
            options=f"-c statement_timeout={self._settings.query_timeout_milliseconds}",
            row_factory=dict_row,
        )

    @staticmethod
    def _assert_current_database(cursor: object) -> None:
        cursor.execute("SELECT current_database() AS database_name")
        row = cursor.fetchone()
        if not isinstance(row, dict) or row.get("database_name") != TARGET_DATABASE:
            raise ActionPreconditionBlockedError()


def _validate_fixed_proposal(proposal: ActionProposalData, mode: ActionMode) -> None:
    """纵深校验固定字段和 digest，禁止篡改后的 Proposal 进入执行器。"""
    target = {"service": "order-service", "scope": "订单慢查询受控靶场"}
    verification_plan = [
        "确认目标索引存在并且固定计划使用目标索引。",
        "固定订单诊断探测恰好执行 3 次，均不得慢查询或超时。",
        "仅聚合这 3 次探测的受限日志，确认无慢查询或超时。",
    ]
    expected_digest = action_digest(
        source_run_id=proposal.source_run_id,
        root_cause_id=proposal.root_cause_id,
        evidence_ids=proposal.evidence_ids,
        target=target,
        verification_plan=verification_plan,
    )
    if (
        proposal.action_id != ORDERS_INDEX_REPAIR_ACTION_ID
        or proposal.mode != mode
        or proposal.target != target
        or proposal.verification_plan != verification_plan
        or proposal.action_digest != expected_digest
    ):
        raise ActionPreconditionBlockedError()


def _plan_uses_seq_scan(plan: object) -> bool:
    node_types, _ = _plan_access_paths(plan)
    return "Seq Scan" in node_types


def _plan_uses_target_index(plan: object) -> bool:
    _, index_names = _plan_access_paths(plan)
    return TARGET_INDEX in index_names


def _plan_access_paths(plan: object) -> tuple[set[str], set[str]]:
    node_types: set[str] = set()
    index_names: set[str] = set()
    _collect_plan_access_paths(plan, node_types, index_names)
    return node_types, index_names


def _collect_plan_access_paths(value: object, node_types: set[str], index_names: set[str]) -> None:
    if isinstance(value, list):
        for item in value:
            _collect_plan_access_paths(item, node_types, index_names)
        return
    if not isinstance(value, dict):
        return
    node_type = value.get("Node Type")
    index_name = value.get("Index Name")
    if isinstance(node_type, str):
        node_types.add(node_type)
    if isinstance(index_name, str):
        index_names.add(index_name)
    for nested_value in value.values():
        _collect_plan_access_paths(nested_value, node_types, index_names)


def _matching_log_facts(path: Path, line_limit: int, request_ids: set[str]) -> dict[str, int]:
    """只聚合三条内部 request id 的日志标量，绝不回传原始记录。"""
    try:
        with path.open("r", encoding="utf-8") as file:
            lines = list(deque(file, maxlen=line_limit))
    except (OSError, UnicodeDecodeError) as error:
        raise ActionVerificationFailedError() from error
    matched_ids: set[str] = set()
    slow_count = 0
    timeout_count = 0
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        request_id = record.get("request_id")
        if (
            request_id not in request_ids
            or record.get("event") != "order_query"
            or record.get("route") != "/orders/diagnostic-probe"
        ):
            continue
        if isinstance(request_id, str):
            matched_ids.add(request_id)
        if record.get("slow_query") is True:
            slow_count += 1
        if record.get("timeout") is True:
            timeout_count += 1
    return {
        "matched_log_count": len(matched_ids),
        "matched_log_slow_query_count": slow_count,
        "matched_log_timeout_count": timeout_count,
    }
