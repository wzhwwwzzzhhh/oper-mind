"""SSE 事件契约与序列化工具。"""

from typing import Literal

from pydantic import BaseModel, Field

from src.api.schemas import TraceEvent, TraceEventType


class DiagnosisProgressEvent(TraceEvent):
    """诊断过程中的一条增量事件。"""

    type: TraceEventType


class DiagnosisCompleteEvent(BaseModel):
    """诊断正常完成事件。"""

    type: Literal["complete"] = "complete"
    result: str
    strategy: str = ""
    trace: list[TraceEvent] = Field(default_factory=list)


class DiagnosisErrorEvent(BaseModel):
    """诊断流发生异常时的结束事件。"""

    type: Literal["error"] = "error"
    code: str
    message: str


def serialize_sse(event_name: str, payload: BaseModel) -> str:
    """把 Pydantic 事件序列化为标准 SSE 文本帧。"""
    return f"event: {event_name}\ndata: {payload.model_dump_json()}\n\n"
