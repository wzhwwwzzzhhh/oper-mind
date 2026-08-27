"""Issue #100 S2 controlled-action real-chain verifier.

Reads the target DSN only from OPERMIND_SERVICE_POSTGRES_TARGET_DSN.
Never prints or persists the DSN, raw SQL, credentials, or raw exceptions.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from uuid import UUID, uuid4

if __package__:
    from ._bootstrap import bootstrap_import_paths
else:
    from _bootstrap import bootstrap_import_paths

bootstrap_import_paths()

from sqlalchemy import text  # noqa: E402

from src.application.controlled_action_catalog import (  # noqa: E402
    COMPOUND_INDEX_TEMPLATE,
    recommendation_id,
)

TARGET_ENV = "OPERMIND_SERVICE_POSTGRES_TARGET_DSN"
HUMAN_GATE_DIR_ENV = "OPERMIND_P8_S2_HUMAN_GATE_DIR"
TARGET_SERVICE = "postgres-target"
TARGET_ACTION_ID = "postgres.orders_compound_index_rebuild.v1"
TARGET_INDEX = "idx_orders_customer_created_at"
TARGET_SCHEMA = "public"
TARGET_TABLE = "orders"
TARGET_COLUMNS = "customer_id,created_at"
TARGET_RISK_SUMMARY = "这是受控靶场结构变更；生产和预发布实例不会执行。"
TARGET_VERIFICATION_PLAN = [
    "确认受控靶场目标表存在",
    "确认固定联合索引存在且有效",
    "只读执行计划确认固定索引可用",
]
TARGET_HOSTS = {"localhost", "127.0.0.1"}
TARGET_PORT = 5433
FORBIDDEN_TARGET_DATABASES = {"gongkar"}
HUMAN_GATE_TIMEOUT_SECONDS = {"approval": 900.0, "execution": 600.0}
HUMAN_GATE_POLL_SECONDS = 0.2
HUMAN_GATE_DECISIONS = {"approval": "approve", "execution": "execute"}
TERMINAL_RUNS = {"succeeded", "failed", "cancelled"}
TERMINAL_PROPOSALS = {"verified", "blocked", "failed", "expired", "rejected"}
_HAS_RUN = False


class SafeStop(RuntimeError):
    """Expected pre-write stop whose message contains no target details."""


class ChainFailure(RuntimeError):
    """Redacted API-chain failure with honest target-write uncertainty."""

    def __init__(self, code: str, *, target_write_may_have_started: bool) -> None:
        super().__init__(code)
        self.code = code
        self.target_write_may_have_started = target_write_may_have_started


@dataclass
class ChainState:
    """Track whether the fixed execution request has been issued."""

    target_write_may_have_started: bool = False


HumanGate = Callable[[str, dict[str, Any]], None]


def require(condition: bool, code: str) -> None:
    if not condition:
        raise SafeStop(code)


def chain_require(condition: bool, code: str, *, target_write_may_have_started: bool) -> None:
    if not condition:
        raise ChainFailure(code, target_write_may_have_started=target_write_may_have_started)


def require_uuid(value: object, code: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as error:
        raise SafeStop(code) from error


def target_dsn() -> str:
    value = os.environ.get(TARGET_ENV)
    require(isinstance(value, str) and bool(value.strip()), "DSN_NOT_IN_PROCESS_ENV")
    return value.strip()


def human_gate_directory() -> Path:
    value = os.environ.get(HUMAN_GATE_DIR_ENV)
    require(isinstance(value, str) and bool(value.strip()), "HUMAN_GATE_DIR_NOT_IN_PROCESS_ENV")
    directory = Path(value).expanduser()
    require(directory.is_absolute(), "HUMAN_GATE_DIR_NOT_ABSOLUTE")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        require(directory.is_dir(), "HUMAN_GATE_DIR_INVALID")
    except SafeStop:
        raise
    except Exception as error:
        raise SafeStop("HUMAN_GATE_DIR_UNAVAILABLE") from error
    return directory.resolve()


def require_human_confirmation(stage: str, summary: dict[str, Any]) -> None:
    """Wait for a human-created response matching a fresh, redacted challenge."""
    require(stage in HUMAN_GATE_DECISIONS, "HUMAN_GATE_STAGE_INVALID")
    directory = human_gate_directory()
    challenge_id = str(uuid4())
    challenge_path = directory / f"p8-s2-{stage}-challenge.json"
    response_path = directory / f"p8-s2-{stage}-response.json"
    challenge = {
        "stage": stage,
        "challenge_id": challenge_id,
        "required_decision": HUMAN_GATE_DECISIONS[stage],
        "expires_in_seconds": int(HUMAN_GATE_TIMEOUT_SECONDS[stage]),
        "summary": summary,
    }
    try:
        with suppress(FileNotFoundError):
            response_path.unlink()
        challenge_path.write_text(json.dumps(challenge, ensure_ascii=False, indent=2), encoding="utf-8")
        deadline = time.monotonic() + HUMAN_GATE_TIMEOUT_SECONDS[stage]
        while time.monotonic() < deadline:
            if not response_path.exists():
                time.sleep(HUMAN_GATE_POLL_SECONDS)
                continue
            try:
                response = json.loads(response_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise SafeStop("HUMAN_GATE_RESPONSE_INVALID") from error
            require(isinstance(response, dict), "HUMAN_GATE_RESPONSE_INVALID")
            require(response.get("stage") == stage, "HUMAN_GATE_STAGE_MISMATCH")
            require(response.get("challenge_id") == challenge_id, "HUMAN_GATE_CHALLENGE_MISMATCH")
            require(response.get("decision") == HUMAN_GATE_DECISIONS[stage], "HUMAN_GATE_DECISION_REJECTED")
            return
        raise SafeStop("HUMAN_GATE_TIMEOUT")
    except SafeStop:
        raise
    except Exception as error:
        raise SafeStop("HUMAN_GATE_UNAVAILABLE") from error
    finally:
        with suppress(OSError):
            challenge_path.unlink()
        with suppress(OSError):
            response_path.unlink()


def validate_boundary(dsn: str) -> None:
    try:
        parsed = urlsplit(dsn)
    except ValueError as error:
        raise SafeStop("TARGET_DSN_INVALID") from error
    require(parsed.scheme in {"postgresql", "postgresql+psycopg"}, "TARGET_SCHEME_MISMATCH")
    require(not parsed.query and not parsed.fragment, "TARGET_DSN_OPTIONS_NOT_ALLOWED")
    require(parsed.hostname in TARGET_HOSTS, "TARGET_HOST_MISMATCH")
    require(bool(parsed.username), "TARGET_USERNAME_MISSING")
    try:
        port = parsed.port
    except ValueError as error:
        raise SafeStop("TARGET_PORT_INVALID") from error
    require(port == TARGET_PORT, "TARGET_PORT_MISMATCH")
    path_segments = parsed.path.split("/")
    require(len(path_segments) >= 2 and bool(path_segments[1]), "TARGET_DATABASE_MISSING")
    require(len(path_segments) == 2, "TARGET_DATABASE_PATH_INVALID")
    database_name = unquote(path_segments[1])
    require("/" not in database_name, "TARGET_DATABASE_PATH_INVALID")
    require(database_name.casefold() not in FORBIDDEN_TARGET_DATABASES, "TARGET_DATABASE_FORBIDDEN")


def normalized_plan(value: object) -> object:
    """Normalize PostgreSQL EXPLAIN JSON without retaining a RowMapping."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def plan_node_types(value: object) -> set[str]:
    found: set[str] = set()
    value = normalized_plan(value)
    if isinstance(value, dict):
        node_type = value.get("Node Type")
        if isinstance(node_type, str):
            found.add(node_type)
        for item in value.values():
            found.update(plan_node_types(item))
    elif isinstance(value, list):
        for item in value:
            found.update(plan_node_types(item))
    return found


def plan_index_names(value: object) -> set[str]:
    found: set[str] = set()
    value = normalized_plan(value)
    if isinstance(value, dict):
        index_name = value.get("Index Name")
        if isinstance(index_name, str):
            found.add(index_name)
        for item in value.values():
            found.update(plan_index_names(item))
    elif isinstance(value, list):
        for item in value:
            found.update(plan_index_names(item))
    return found


def plan_uses_target_index_scan(value: object) -> bool:
    """Require the target index name and accepted scan type on the same plan node."""
    value = normalized_plan(value)
    if isinstance(value, dict):
        if (
            value.get("Node Type") in {"Index Scan", "Index Only Scan"}
            and value.get("Index Name") == TARGET_INDEX
        ):
            return True
        return any(plan_uses_target_index_scan(item) for item in value.values())
    if isinstance(value, list):
        return any(plan_uses_target_index_scan(item) for item in value)
    return False


def read_target_facts(dsn: str) -> dict[str, bool]:
    from src.infrastructure.services.postgres_engine import create_read_only_postgres_engine

    engine: Any | None = None
    connection: Any | None = None
    try:
        engine = create_read_only_postgres_engine(dsn)
        connection = engine.connect()
        connection.execute(text("SET TRANSACTION READ ONLY"))
        table_exists = connection.execute(text("SELECT to_regclass('public.orders') IS NOT NULL")).scalar() is True
        columns_ok = connection.execute(
            text(
                "SELECT COUNT(*) = 2 FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'orders' "
                "AND column_name IN ('customer_id', 'created_at')"
            )
        ).scalar() is True
        index_exists = connection.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_class index_ref "
                "JOIN pg_index ON pg_index.indexrelid = index_ref.oid "
                "JOIN pg_class table_ref ON table_ref.oid = pg_index.indrelid "
                "JOIN pg_namespace index_ns ON index_ns.oid = index_ref.relnamespace "
                "JOIN pg_namespace table_ns ON table_ns.oid = table_ref.relnamespace "
                "WHERE index_ns.nspname = 'public' AND table_ns.nspname = 'public' "
                "AND table_ref.relname = 'orders' AND index_ref.relname = 'idx_orders_customer_created_at')"
            )
        ).scalar() is True
        index_valid = connection.execute(
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
        nodes: set[str] = set()
        target_index_scan = False
        if table_exists and columns_ok:
            rows = connection.execute(
                text(
                    "EXPLAIN (FORMAT JSON) SELECT customer_id, created_at FROM public.orders "
                    "WHERE customer_id = 1 ORDER BY created_at"
                )
            ).mappings().all()
            for row in rows:
                plan = row.get("QUERY PLAN") or row.get("query plan")
                nodes.update(plan_node_types(plan))
                target_index_scan = target_index_scan or plan_uses_target_index_scan(plan)
        return {
            "table_exists": table_exists,
            "columns_ok": columns_ok,
            "index_exists": index_exists,
            "index_valid": index_valid,
            "plan_seq_scan": "Seq Scan" in nodes,
            "plan_index_scan": target_index_scan,
            "plan_uses_target_index": target_index_scan,
        }
    except SafeStop:
        raise
    except Exception as error:
        raise SafeStop("TARGET_READ_UNAVAILABLE") from error
    finally:
        if connection is not None:
            connection.close()
        if engine is not None:
            engine.dispose()


def _debug_http(response: Any, expected_status: int) -> None:
    """Optionally log only method/path/status when P8_S2_DEBUG_LOG is set."""
    log_path = os.environ.get("P8_S2_DEBUG_LOG")
    if not log_path:
        return
    try:
        request = getattr(response, "request", None)
        method = str(getattr(request, "method", "?"))
        url = str(getattr(request, "url", "?"))
        path = url.split("?", 1)[0]
        offset = path.rfind("/api/v1/")
        short = path[offset:] if offset >= 0 else path
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"{method} {short} -> {response.status_code} (expected {expected_status})\n")
    except Exception:
        return


def safe_json(response: Any, expected_status: int, *, target_write_may_have_started: bool = False) -> dict[str, Any]:
    _debug_http(response, expected_status)
    if response.status_code != expected_status:
        raise ChainFailure(
            f"HTTP_{response.status_code}_EXPECTED_{expected_status}",
            target_write_may_have_started=target_write_may_have_started,
        )
    try:
        value = response.json()
    except Exception as error:
        raise ChainFailure(
            "INVALID_JSON_RESPONSE",
            target_write_may_have_started=target_write_may_have_started,
        ) from error
    if not isinstance(value, dict):
        raise ChainFailure(
            "INVALID_RESPONSE_SHAPE",
            target_write_may_have_started=target_write_may_have_started,
        )
    return value


def poll_run(client: Any, run_id: str) -> dict[str, Any]:
    for _ in range(60):
        body = safe_json(client.get(f"/api/v1/runs/{run_id}"), 200)
        run = body.get("run")
        require(isinstance(run, dict), "RUN_RESPONSE_MISSING")
        if run.get("status") in TERMINAL_RUNS:
            return run
        time.sleep(0.1)
    raise SafeStop("RUN_TIMEOUT")


def poll_proposal(
    client: Any,
    proposal_id: str,
    *,
    target_write_may_have_started: bool = False,
) -> dict[str, Any]:
    for _ in range(100):
        body = safe_json(
            client.get(f"/api/v1/action-proposals/{proposal_id}"),
            200,
            target_write_may_have_started=target_write_may_have_started,
        )
        proposal = body.get("proposal")
        require(isinstance(proposal, dict), "PROPOSAL_RESPONSE_MISSING")
        if proposal.get("status") in TERMINAL_PROPOSALS:
            return proposal
        time.sleep(0.1)
    raise SafeStop("PROPOSAL_TIMEOUT")


def dispose_session_factory(factory: Any) -> None:
    """Release the temporary metadata engine so Windows can remove its file."""
    settings = getattr(factory, "kw", {})
    engine = settings.get("bind") if isinstance(settings, dict) else None
    if engine is not None:
        engine.dispose()


def run_api_chain(
    *,
    chain_state: ChainState | None = None,
    human_gate: HumanGate = require_human_confirmation,
) -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from src import app as api_module

    original_services = api_module.app.state.v1_services
    scoped_services = replace(original_services, monitor_sampler=None)
    api_module.app.state.v1_services = scoped_services
    state = chain_state or ChainState()
    try:
        client_context = TestClient(api_module.app, raise_server_exceptions=False)
        client = client_context.__enter__()
        try:
            api_result = run_api_chain_with_client(client, chain_state=state, human_gate=human_gate)
        except BaseException as error:
            # Preserve the body error if teardown also fails. TestClient ignores
            # exc_info today, but pass it to honor the context-manager protocol.
            with suppress(BaseException):
                client_context.__exit__(type(error), error, error.__traceback__)
            if state.target_write_may_have_started:
                if isinstance(error, ChainFailure) and error.target_write_may_have_started:
                    raise
                code = error.code if isinstance(error, ChainFailure) else str(error)
                if not isinstance(error, (SafeStop, ChainFailure)):
                    code = "API_CHAIN_UNEXPECTED_AFTER_EXECUTION_REQUEST"
                raise ChainFailure(code, target_write_may_have_started=True) from error
            raise
        try:
            client_context.__exit__(None, None, None)
        except BaseException as error:
            raise ChainFailure(
                "API_CHAIN_TEARDOWN_FAILED",
                target_write_may_have_started=True,
            ) from error
        return api_result
    finally:
        api_module.app.state.v1_services = original_services
        with suppress(Exception):
            dispose_session_factory(scoped_services.session_factory)


def run_api_chain_with_client(
    client: Any,
    *,
    chain_state: ChainState | None = None,
    human_gate: HumanGate = require_human_confirmation,
) -> dict[str, Any]:
    """Drive the public API with explicit human approval and execution gates."""
    session_body = safe_json(
        client.post(
            "/api/v1/sessions",
            json={"title": "Issue #100 S2 controlled target review", "service_id": TARGET_SERVICE},
        ),
        201,
    )
    session = session_body.get("session")
    require(isinstance(session, dict), "SESSION_RESPONSE_MISSING")
    session_id = require_uuid(session.get("id"), "SESSION_ID_INVALID")
    require(session.get("service_id") == TARGET_SERVICE, "SESSION_TARGET_SERVICE_MISMATCH")

    run_body = safe_json(
        client.post(
            f"/api/v1/sessions/{session_id}/runs",
            headers={"Idempotency-Key": str(uuid4())},
            json={
                "query": "排查受控靶场 orders 慢查询 seq scan，分析固定查询的索引缺失信号",
                "service_id": TARGET_SERVICE,
            },
        ),
        202,
    )
    accepted_run = run_body.get("run")
    require(isinstance(accepted_run, dict), "RUN_ACCEPT_RESPONSE_MISSING")
    run_id = require_uuid(accepted_run.get("id"), "RUN_ID_INVALID")
    require(accepted_run.get("service_id") == TARGET_SERVICE, "RUN_TARGET_SERVICE_MISMATCH")
    run = poll_run(client, run_id)
    require(run.get("status") == "succeeded", "RUN_NOT_SUCCEEDED")
    require(run.get("service_id") == TARGET_SERVICE, "RUN_TARGET_SERVICE_MISMATCH")

    result = run.get("result")
    require(isinstance(result, dict), "STRUCTURED_RESULT_MISSING")
    evidence = result.get("evidence")
    require(isinstance(evidence, list), "STRUCTURED_EVIDENCE_MISSING")
    evidence_by_id = {
        item.get("id"): item
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    recommendations = result.get("recommendations")
    require(isinstance(recommendations, list) and len(recommendations) == 1, "STRUCTURED_RECOMMENDATION_MISMATCH")
    recommendation = recommendations[0]
    require(isinstance(recommendation, dict), "STRUCTURED_RECOMMENDATION_MISMATCH")
    recommendation_evidence_ids = recommendation.get("evidence_ids")
    require(
        isinstance(recommendation_evidence_ids, list) and len(recommendation_evidence_ids) == 3,
        "STRUCTURED_RECOMMENDATION_EVIDENCE_MISMATCH",
    )
    referenced_evidence = [evidence_by_id.get(item_id) for item_id in recommendation_evidence_ids]
    require(
        all(isinstance(item, dict) for item in referenced_evidence)
        and {item.get("title") for item in referenced_evidence if isinstance(item, dict)}
        == {"目标表存在", "固定联合索引缺失", "顺序扫描信号"}
        and all(
            item.get("source_type") == "database" and item.get("source_name") == "postgres_read_only"
            for item in referenced_evidence
            if isinstance(item, dict)
        ),
        "STRUCTURED_RECOMMENDATION_EVIDENCE_MISMATCH",
    )
    require(
        recommendation
        == {
            "id": str(recommendation_id(TARGET_ACTION_ID)),
            "title": COMPOUND_INDEX_TEMPLATE.recommendation_title,
            "description": COMPOUND_INDEX_TEMPLATE.recommendation_description,
            "priority": COMPOUND_INDEX_TEMPLATE.recommendation_priority,
            "risk_level": COMPOUND_INDEX_TEMPLATE.recommendation_risk_level,
            "requires_approval": True,
            "evidence_ids": recommendation_evidence_ids,
        },
        "STRUCTURED_RECOMMENDATION_MISMATCH",
    )
    require(
        result.get("impact")
        == {
            "summary": COMPOUND_INDEX_TEMPLATE.impact_summary,
            "affected_services": [TARGET_SERVICE],
            "affected_scope": COMPOUND_INDEX_TEMPLATE.impact_scope,
        },
        "STRUCTURED_IMPACT_MISMATCH",
    )
    require(result.get("requires_approval") is True, "STRUCTURED_APPROVAL_FLAG_MISMATCH")

    proposal_body = safe_json(client.get(f"/api/v1/runs/{run_id}/action-proposal"), 200)
    proposal = proposal_body.get("proposal")
    require(isinstance(proposal, dict), "PROPOSAL_NOT_CREATED")
    proposal_id = require_uuid(proposal.get("id"), "PROPOSAL_ID_INVALID")
    require(proposal.get("source_run_id") == run_id, "PROPOSAL_SOURCE_RUN_MISMATCH")
    require(proposal.get("action_id") == TARGET_ACTION_ID, "PROPOSAL_ACTION_ID_MISMATCH")
    require(proposal.get("mode") == "target", "PROPOSAL_NOT_TARGET_MODE")
    require(proposal.get("status") == "pending_approval", "PROPOSAL_NOT_PENDING_APPROVAL")
    expected_target = {
        "service_id": TARGET_SERVICE,
        "schema": TARGET_SCHEMA,
        "table": TARGET_TABLE,
        "columns": TARGET_COLUMNS,
        "index_name": TARGET_INDEX,
    }
    require(proposal.get("target") == expected_target, "PROPOSAL_TARGET_MISMATCH")
    action_digest = proposal.get("action_digest")
    require(isinstance(action_digest, str) and len(action_digest) == 64, "PROPOSAL_DIGEST_INVALID")
    risk_summary = proposal.get("risk_summary")
    require(risk_summary == TARGET_RISK_SUMMARY, "PROPOSAL_RISK_SUMMARY_MISMATCH")
    verification_plan = proposal.get("verification_plan")
    require(verification_plan == TARGET_VERIFICATION_PLAN, "PROPOSAL_VERIFICATION_PLAN_MISMATCH")
    human_gate(
        "approval",
        {
            "proposal_id": proposal_id,
            "action_id": TARGET_ACTION_ID,
            "action_digest": action_digest,
            "target": expected_target,
            "risk_summary": risk_summary,
            "verification_plan": verification_plan,
        },
    )

    approved_body = safe_json(
        client.post(
            f"/api/v1/action-proposals/{proposal_id}/approval",
            headers={"Idempotency-Key": str(uuid4())},
            json={"decision": "approve"},
        ),
        200,
    )
    approved = approved_body.get("proposal")
    require(isinstance(approved, dict) and approved.get("status") == "approved", "APPROVAL_NOT_RECORDED")
    approval = approved.get("approval") or {}
    require(approval.get("actor") == "local_operator", "APPROVAL_ACTOR_MISMATCH")
    require(approval.get("decision") == "approve", "APPROVAL_DECISION_MISMATCH")
    require(approval.get("action_digest") == action_digest, "APPROVAL_DIGEST_MISMATCH")
    human_gate(
        "execution",
        {
            "proposal_id": proposal_id,
            "action_id": TARGET_ACTION_ID,
            "action_digest": action_digest,
            "target": expected_target,
            "approval_actor": approval.get("actor"),
            "approval_decision": approval.get("decision"),
        },
    )

    try:
        if chain_state is not None:
            chain_state.target_write_may_have_started = True
        safe_json(
            client.post(
                f"/api/v1/action-proposals/{proposal_id}/executions",
                headers={"Idempotency-Key": str(uuid4())},
                json={},
            ),
            202,
            target_write_may_have_started=True,
        )
        final_proposal = poll_proposal(client, proposal_id, target_write_may_have_started=True)
        require(final_proposal.get("status") == "verified", "PROPOSAL_NOT_VERIFIED")
        execution = final_proposal.get("execution") or {}
        verification = final_proposal.get("verification") or {}
        facts = verification.get("facts") or {}
        execution_id = require_uuid(execution.get("id"), "EXECUTION_ID_INVALID")
        require(execution.get("proposal_id") == proposal_id, "EXECUTION_PROPOSAL_MISMATCH")
        require(verification.get("execution_id") == execution_id, "VERIFICATION_EXECUTION_MISMATCH")
        require(execution.get("mode") == "target", "EXECUTION_NOT_TARGET_MODE")
        require(execution.get("status") == "succeeded", "EXECUTION_NOT_SUCCEEDED")
        require(verification.get("mode") == "target", "VERIFICATION_NOT_TARGET_MODE")
        require(verification.get("status") == "verified", "VERIFICATION_NOT_VERIFIED")
        require(
            facts.get("index_exists") is True
            and facts.get("index_valid") is True
            and facts.get("plan_uses_index") is True,
            "VERIFICATION_FACTS_INCOMPLETE",
        )

        events_body = safe_json(
            client.get(f"/api/v1/action-proposals/{proposal_id}/events?limit=100"),
            200,
            target_write_may_have_started=True,
        )
        events = events_body.get("items")
        chain_require(isinstance(events, list), "ACTION_EVENTS_MISSING", target_write_may_have_started=True)
        chain_require(
            all(isinstance(item, dict) for item in events),
            "ACTION_EVENT_SHAPE_INVALID",
            target_write_may_have_started=True,
        )
        chain_require(
            all(item.get("proposal_id") == proposal_id for item in events),
            "ACTION_EVENT_PROPOSAL_MISMATCH",
            target_write_may_have_started=True,
        )
        sequences = [item.get("sequence") for item in events]
        chain_require(
            all(isinstance(sequence, int) and not isinstance(sequence, bool) and sequence >= 1 for sequence in sequences),
            "ACTION_EVENT_SEQUENCE_INVALID",
            target_write_may_have_started=True,
        )
        chain_require(
            sequences == list(range(1, len(sequences) + 1)),
            "ACTION_EVENT_SEQUENCE_OUT_OF_ORDER",
            target_write_may_have_started=True,
        )
        event_types = [str(item.get("type")) for item in events]
        required_events = {
            "proposal_created",
            "approval_recorded",
            "execution_requested",
            "execution_started",
            "precondition_checked",
            "execution_completed",
            "verification_started",
            "verification_completed",
        }
        chain_require(
            required_events.issubset(set(event_types)),
            "ACTION_EVENT_CHAIN_INCOMPLETE",
            target_write_may_have_started=True,
        )
        chain_require(
            all(event_types.count(event_type) == 1 for event_type in required_events),
            "ACTION_EVENT_CHAIN_DUPLICATED",
            target_write_may_have_started=True,
        )
        required_order = [
            "proposal_created",
            "approval_recorded",
            "execution_requested",
            "execution_started",
            "precondition_checked",
            "execution_completed",
            "verification_started",
            "verification_completed",
        ]
        positions = [event_types.index(event_type) for event_type in required_order]
        chain_require(
            positions == sorted(positions),
            "ACTION_EVENT_CHAIN_OUT_OF_ORDER",
            target_write_may_have_started=True,
        )

        return {
            "session_id": session_id,
            "run_id": run_id,
            "proposal_id": proposal_id,
            "execution_id": execution_id,
            "run_status": run.get("status"),
            "structured_result": {
                "recommendation_count": len(recommendations),
                "recommendation_id": recommendation.get("id"),
                "evidence_count": len(recommendation_evidence_ids),
                "impact_present": result.get("impact") is not None,
                "requires_approval": result.get("requires_approval"),
            },
            "proposal_status": final_proposal.get("status"),
            "proposal_target_matched": True,
            "approval_digest_matched": True,
            "approval_actor": (final_proposal.get("approval") or {}).get("actor"),
            "execution_mode": execution.get("mode"),
            "execution_status": execution.get("status"),
            "verification_mode": verification.get("mode"),
            "verification_status": verification.get("status"),
            "verification_facts": {
                "index_exists": facts.get("index_exists"),
                "index_valid": facts.get("index_valid"),
                "plan_uses_index": facts.get("plan_uses_index"),
            },
            "action_event_types": event_types,
        }
    except ChainFailure:
        raise
    except SafeStop as error:
        raise ChainFailure(str(error), target_write_may_have_started=True) from error
    except Exception as error:
        raise ChainFailure(
            "API_CHAIN_UNEXPECTED_AFTER_EXECUTION_REQUEST",
            target_write_may_have_started=True,
        ) from error


def main() -> int:
    global _HAS_RUN
    target_write_may_have_started = False
    if _HAS_RUN:
        print(
            json.dumps(
                {"result": "SAFE_STOP", "code": "VERIFIER_PROCESS_ALREADY_USED", "target_write_may_have_started": False},
                ensure_ascii=False,
            )
        )
        return 2
    _HAS_RUN = True
    try:
        dsn = target_dsn()
        validate_boundary(dsn)
        preflight = read_target_facts(dsn)
        require(preflight["table_exists"], "TARGET_TABLE_MISSING")
        require(preflight["columns_ok"], "TARGET_COLUMNS_MISSING")
        require(not preflight["index_valid"], "TARGET_INDEX_ALREADY_EXISTS")
        require(not preflight["index_exists"], "TARGET_INDEX_INVALID_REMAINS")
        require(preflight["plan_seq_scan"], "PREFLIGHT_NOT_SEQ_SCAN")

        api_result: dict[str, Any] | None = None
        chain_state = ChainState()
        try:
            with tempfile.TemporaryDirectory(prefix="opermind-p8-s2-") as temp_dir:
                database_path = Path(temp_dir) / "metadata.sqlite3"
                os.environ["OPERMIND_APP_DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
                os.environ["OPERMIND_API_KEY"] = "mock"
                os.environ["OPERMIND_BASE_URL"] = "http://mock"
                os.environ["OPERMIND_MODEL"] = "mock"

                from src.infrastructure.persistence import models as _models  # noqa: F401
                from src.infrastructure.persistence.database import Base, create_persistence_runtime

                runtime = create_persistence_runtime(os.environ["OPERMIND_APP_DATABASE_URL"])
                Base.metadata.create_all(runtime.engine)
                runtime.engine.dispose()

                api_result = run_api_chain(chain_state=chain_state)
                target_write_may_have_started = True
        except (SafeStop, ChainFailure):
            raise
        except Exception as error:
            if chain_state.target_write_may_have_started or api_result is not None:
                raise ChainFailure(
                    "TEMP_METADATA_CLEANUP_FAILED",
                    target_write_may_have_started=True,
                ) from error
            raise

        try:
            postflight = read_target_facts(dsn)
            chain_require(postflight["index_valid"], "POSTFLIGHT_INDEX_MISSING", target_write_may_have_started=True)
            chain_require(postflight["plan_index_scan"], "POSTFLIGHT_NOT_INDEX_SCAN", target_write_may_have_started=True)
            chain_require(postflight["plan_uses_target_index"], "POSTFLIGHT_WRONG_INDEX", target_write_may_have_started=True)
        except ChainFailure:
            raise
        except SafeStop as error:
            raise ChainFailure(str(error), target_write_may_have_started=True) from error

        evidence = {
            "result": "PASS",
            "boundary": {
                "service_id": TARGET_SERVICE,
                "host_scope": "localhost",
                "port": TARGET_PORT,
                "database_scope": "authorized_nonempty_database",
                "schema": "public",
                "table": "orders",
                "columns": ["customer_id", "created_at"],
                "index_name": TARGET_INDEX,
            },
            "preflight": preflight,
            "api_chain": api_result,
            "postflight": postflight,
            "limitations": [
                "LLM provider ran in deterministic mock mode; PostgreSQL collector, DDL executor, independent Verify, API, persistence, approval and audit paths were real.",
                "The verifier does not drop or otherwise clean up the created target index.",
            ],
        }
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 0
    except SafeStop as error:
        print(
            json.dumps(
                {"result": "SAFE_STOP", "code": str(error), "target_write_may_have_started": False},
                ensure_ascii=False,
            )
        )
        return 2
    except ChainFailure as error:
        print(
            json.dumps(
                {
                    "result": "FAIL",
                    "code": error.code,
                    "target_write_may_have_started": error.target_write_may_have_started,
                },
                ensure_ascii=False,
            )
        )
        return 1
    except Exception:
        print(
            json.dumps(
                {
                    "result": "FAIL",
                    "code": "UNEXPECTED_SAFE_REDACTED_FAILURE",
                    "target_write_may_have_started": target_write_may_have_started,
                },
                ensure_ascii=False,
            )
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
