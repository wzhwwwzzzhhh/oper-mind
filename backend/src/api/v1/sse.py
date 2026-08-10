"""P2.4 v1 持久化 RunEvent 的 SSE 序列化与重放工具。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from time import sleep
from uuid import UUID

from src.api.v1.schemas import RunEventEnvelope
from src.domain.diagnosis import RUN_TERMINAL_STATUSES
from src.domain.records import RunEventCursor, RunEventData
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.repositories import SqlAlchemyDiagnosisRunRepository, SqlAlchemyRunEventRepository

POLL_INTERVAL_SECONDS = 0.05
EVENT_PAGE_SIZE = 100


def serialize_run_event(sequence: int, payload: RunEventEnvelope) -> str:
    """序列化严格对应一条持久化事件的标准 SSE 帧。"""
    return f"id: {sequence}\nevent: run_event\ndata: {payload.model_dump_json()}\n\n"


def replay_run_events(
    session_factory: SessionFactory,
    run_id: UUID,
    after_sequence: int,
    envelope_factory: Callable[[RunEventData], RunEventEnvelope],
) -> Iterator[str]:
    """只重放已提交事件；Run 终态且终态事件发出后关闭流。"""
    current_sequence = after_sequence
    while True:
        session = session_factory()
        try:
            run = SqlAlchemyDiagnosisRunRepository(session).get_by_id(run_id)
            if run is None:
                return
            page = SqlAlchemyRunEventRepository(session).list_by_run(
                run_id,
                RunEventCursor(sequence=current_sequence) if current_sequence else None,
                EVENT_PAGE_SIZE,
            )
        finally:
            session.close()

        for event in page.items:
            current_sequence = event.sequence
            yield serialize_run_event(event.sequence, envelope_factory(event))
            if event.type.value in {"run_succeeded", "run_failed", "run_cancelled"}:
                return

        if run.status in RUN_TERMINAL_STATUSES:
            return
        sleep(POLL_INTERVAL_SECONDS)


def parse_event_sequence(value: str | int | None) -> int | None:
    """解析 Last-Event-ID 或 after_sequence，允许 0 代表从最早事件开始。"""
    if value is None:
        return None
    text = str(value)
    if not text.isdecimal():
        raise ValueError("事件游标必须是非负整数")
    return int(text)
