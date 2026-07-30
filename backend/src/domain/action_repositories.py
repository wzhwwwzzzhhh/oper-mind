"""P4.2 固定修复提案与审计的 Repository 端口。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from src.domain.actions import (
    ActionApprovalData,
    ActionEventCursor,
    ActionEventData,
    ActionExecutionData,
    ActionExecutionStatus,
    ActionIdempotencyKeyData,
    ActionProposalData,
    ActionProposalStatus,
    ActionVerificationData,
)
from src.domain.records import RepositoryPage


class ActionProposalRepository(Protocol):
    """固定修复 Proposal 持久化端口。"""

    def add(self, proposal: ActionProposalData) -> None: ...
    def get_by_id(self, proposal_id: UUID) -> ActionProposalData | None: ...
    def get_by_source_run_id(self, run_id: UUID) -> ActionProposalData | None: ...
    def transition_status(
        self,
        proposal_id: UUID,
        expected_statuses: set[ActionProposalStatus],
        status: ActionProposalStatus,
        *,
        updated_at: datetime,
        approved_at: datetime | None = None,
        expires_at: datetime | None = None,
        execution_started_at: datetime | None = None,
        completed_at: datetime | None = None,
        failure_code: str | None = None,
        failure_message: str | None = None,
    ) -> ActionProposalData | None: ...
    def reserve_event_sequence(self, proposal_id: UUID) -> int | None: ...


class ActionApprovalRepository(Protocol):
    """单次审批记录端口。"""

    def add(self, approval: ActionApprovalData) -> None: ...
    def get_by_proposal_id(self, proposal_id: UUID) -> ActionApprovalData | None: ...


class ActionExecutionRepository(Protocol):
    """固定执行记录端口。"""

    def add(self, execution: ActionExecutionData) -> None: ...
    def get_by_proposal_id(self, proposal_id: UUID) -> ActionExecutionData | None: ...
    def get_by_id(self, execution_id: UUID) -> ActionExecutionData | None: ...
    def transition_status(
        self,
        execution_id: UUID,
        expected_statuses: set[ActionExecutionStatus],
        status: ActionExecutionStatus,
        *,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        precondition_summary: str | None = None,
        action_summary: str | None = None,
        failure_code: str | None = None,
        failure_message: str | None = None,
    ) -> ActionExecutionData | None: ...


class ActionVerificationRepository(Protocol):
    """独立 Verify 记录端口。"""

    def add(self, verification: ActionVerificationData) -> None: ...
    def get_by_execution_id(self, execution_id: UUID) -> ActionVerificationData | None: ...


class ActionEventRepository(Protocol):
    """Proposal 审计事件端口。"""

    def add(self, event: ActionEventData) -> None: ...
    def list_by_proposal(
        self, proposal_id: UUID, cursor: ActionEventCursor | None, limit: int
    ) -> RepositoryPage[ActionEventData, ActionEventCursor]: ...


class ActionIdempotencyKeyRepository(Protocol):
    """审批和执行 POST 的幂等记录端口。"""

    def add(self, key: ActionIdempotencyKeyData) -> None: ...
    def get_by_scope(
        self, proposal_id: UUID, endpoint: str, idempotency_key: UUID
    ) -> ActionIdempotencyKeyData | None: ...
