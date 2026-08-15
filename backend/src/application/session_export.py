"""P8 会话导出——只读聚合安全摘要 Markdown 文档用例。

导出内容只含既有公开投影字段的安全子集（会话标题/时间线消息正文、Run 结论摘要、
证据摘要），不含 CoT/Prompt、原始工具输出、原始 SQL、原始异常、凭据或完整连接细节；
进入文档的文本字段（标题/消息正文/摘要/报告/证据）统一过共享 ``desensitize()`` 兜底
脱敏，并在成文后叠加导出专用连接串规则（覆盖无凭据完整 DSN），作为最后一道防线
（``service_id`` 等标量沿用既有公开投影口径，不构成新增暴露）。

确定性：文档只含稳定字段（会话标题/创建时间/状态、消息时间线、Run 摘要），
不含导出时间戳或随机标识符——相同会话重复导出字节一致（AC7）。
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from uuid import UUID

from pydantic import BaseModel, JsonValue
from sqlalchemy.exc import SQLAlchemyError

from src.application.errors import SessionExportUnavailableError, SessionNotFoundError
from src.core.tool_gateway import desensitize
from src.domain.diagnosis import MessageRole, RunStatus
from src.domain.records import (
    DiagnosisResultData,
    DiagnosisRunData,
    MessageData,
    SessionData,
)
from src.domain.repositories import SessionExportStore

MESSAGE_EXPORT_CAP = 500
RUN_EXPORT_CAP = 200
EVIDENCE_PER_RUN_CAP = 50

# 导出专用连接串兜底规则：覆盖共享 desensitize() 未命中的**无凭据**完整 DSN
# （如 ``postgresql://prod-db:5432/app``）。命中即整段替换为占位符，
# 绝不把主机/库名带出导出文档。不改动共享 desensitize() 的既有规则。
_CONNECTION_STRING_PATTERN = re.compile(
    r"(?i)\b(?:postgres|postgresql|mysql|redis|mongodb|mssql)://[^\s]+|jdbc:[^\s]+"
)
_CONNECTION_STRING_REDACTED = "[已脱敏:连接串]"

# 失败 Run 的安全错误（与 resources._safe_run_error 白名单同口径；如有扩充需同步）。
_EXPORT_SAFE_ERROR = "诊断执行失败，请稍后重试"


def _safe_export_run_error(_code: str | None, _message: str | None) -> str:
    """把失败 Run 的错误收敛为白名单安全文案，绝不透传原始错误文本。"""
    return _EXPORT_SAFE_ERROR


def _role_label(role: MessageRole, run_id: UUID | None) -> str:
    """把消息角色映射为导出文档的中文小节标题。"""
    if role == MessageRole.USER:
        return "用户"
    if role == MessageRole.SYSTEM:
        return "系统提醒"
    return "OperMind · 调查" if run_id is not None else "OperMind · 普通对话"


def _evidence_line(item: Mapping[str, JsonValue]) -> str:
    """把一条结构化证据收敛为一行安全摘要（仅 source_type/title/summary）。"""
    source_type = item.get("source_type")
    title = item.get("title")
    summary = item.get("summary")
    source = str(source_type) if isinstance(source_type, str) and source_type else "evidence"
    title_text = str(title) if isinstance(title, str) and title else "（无标题证据）"
    summary_text = str(summary) if isinstance(summary, str) and summary else "（无摘要）"
    return f"- [{source}] {desensitize(title_text)}：{desensitize(summary_text)}"


def _run_summary_block(
    index: int,
    run: DiagnosisRunData,
    result: DiagnosisResultData | None,
    messages_by_id: dict[UUID, MessageData],
) -> list[str]:
    """把一个 Run 收敛为调查摘要区的一组 Markdown 行。"""
    lines = [f"### 第 {index} 次调查（{run.created_at.isoformat()}）"]
    input_message = messages_by_id.get(run.input_message_id)
    if input_message is not None:
        lines.append(f"**问题**：{desensitize(input_message.content)}")
    lines.append(f"**状态**：{run.status.value}")
    lines.append(f"**目标服务**：{run.service_id if run.service_id else '未关联服务'}")
    if run.status == RunStatus.FAILED:
        lines.append(f"**错误**：{_safe_export_run_error(run.error_code, run.error_message)}")
    if result is not None:
        lines.append(f"**严重度**：{result.severity.value}")
        lines.append(f"**置信度**：{result.confidence}")
        lines.append(f"**结论**：{desensitize(result.summary)}")
        if result.report_markdown:
            lines.append("**报告**：")
            lines.append(desensitize(result.report_markdown))
        evidence = result.evidence
        if evidence:
            lines.append("**证据摘要**：")
            shown = evidence[:EVIDENCE_PER_RUN_CAP]
            lines.extend(_evidence_line(item) for item in shown)
            if len(evidence) > EVIDENCE_PER_RUN_CAP:
                lines.append(f"…等 {len(evidence)} 条证据")
    return lines


def build_session_export_markdown(
    *,
    session: SessionData,
    messages: list[MessageData],
    runs_with_results: list[tuple[DiagnosisRunData, DiagnosisResultData | None]],
    messages_truncated: bool,
    runs_truncated: bool,
) -> str:
    """把会话聚合为确定性 Markdown 安全摘要文档（纯函数，可独立单测）。

    空态：无消息且无 Run 时返回「导出头 + 无可导出内容」，不伪造内容。
    """
    truncation_notes = []
    if messages_truncated:
        truncation_notes.append(f"仅导出最近 {MESSAGE_EXPORT_CAP} 条消息")
    if runs_truncated:
        truncation_notes.append(f"仅导出最近 {RUN_EXPORT_CAP} 次调查")
    note_suffix = " · " + " / ".join(truncation_notes) if truncation_notes else ""

    lines = [
        f"# {desensitize(session.title)}",
        "",
        "> 会话导出 · OperMind 安全摘要（仅含脱敏投影，不含原始证据）",
        f"> 创建时间：{session.created_at.isoformat()}",
        f"> 状态：{session.status.value}",
        f"> 消息 {len(messages)} 条 · 调查 {len(runs_with_results)} 次{note_suffix}",
    ]

    if not messages and not runs_with_results:
        lines.extend(["", "## 无可导出内容", "", "该会话没有可导出的对话内容。"])
        return _finalize_document(lines)

    if messages:
        lines.extend(["", "## 对话时间线"])
        for message in messages:
            lines.extend(
                [
                    "",
                    f"### {_role_label(message.role, message.run_id)}",
                    f"> {message.created_at.isoformat()}",
                    desensitize(message.content),
                ]
            )

    if runs_with_results:
        lines.extend(["", f"## 调查摘要（共 {len(runs_with_results)} 次）"])
        messages_by_id = {message.id: message for message in messages}
        for index, (run, result) in enumerate(runs_with_results, start=1):
            lines.extend(["", *_run_summary_block(index, run, result, messages_by_id)])

    return _finalize_document(lines)


def _finalize_document(lines: list[str]) -> str:
    """对成文做最后一道脱敏（连接串兜底）后拼装为文档。"""
    text = "\n".join(lines)
    return _CONNECTION_STRING_PATTERN.sub(_CONNECTION_STRING_REDACTED, text) + "\n"


class SessionExportDocument(BaseModel):
    """会话导出的聚合结果（跨层数据，显式契约）。"""

    markdown: str
    empty: bool


class SessionExportApplicationService:
    """会话导出用例：单会话只读聚合 + 安全摘要文档构建。

    数据源经 ``SessionExportStore`` 端口工厂注入（装配在 ``api/v1/dependencies.py``，
    对齐 ``audit_service.py`` 只读服务先例）；持久化读取失败统一转为
    ``SessionExportUnavailableError``（路由映射 503），绝不返回半截文档。
    """

    def __init__(self, store_factory: Callable[[], SessionExportStore]) -> None:
        self._store_factory = store_factory

    def render_markdown(self, session_id: UUID) -> SessionExportDocument:
        """读取会话聚合数据并构建导出文档；会话不存在抛 ``SessionNotFoundError``。

        读取与构建任一步失败都收敛为 ``SessionExportUnavailableError``（503），
        绝不返回半截文档。
        """
        store = None
        try:
            store = self._store_factory()
            value = store.get_session(session_id)
            if value is None:
                raise SessionNotFoundError()
            messages = store.list_latest_messages(session_id, MESSAGE_EXPORT_CAP + 1)
            messages_truncated = len(messages) > MESSAGE_EXPORT_CAP
            messages = messages[-MESSAGE_EXPORT_CAP:]
            runs = store.list_latest_runs(session_id, RUN_EXPORT_CAP + 1)
            runs_truncated = len(runs) > RUN_EXPORT_CAP
            runs = runs[-RUN_EXPORT_CAP:]
            runs_with_results = [(run, store.get_result(run.id)) for run in runs]
            markdown = build_session_export_markdown(
                session=value,
                messages=messages,
                runs_with_results=runs_with_results,
                messages_truncated=messages_truncated,
                runs_truncated=runs_truncated,
            )
        except (SQLAlchemyError, ValueError) as error:
            raise SessionExportUnavailableError() from error
        finally:
            if store is not None:
                store.close()
        return SessionExportDocument(markdown=markdown, empty=not messages and not runs_with_results)
