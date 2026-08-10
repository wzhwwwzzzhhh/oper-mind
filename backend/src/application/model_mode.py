"""P8 模型运行时模式应用服务与生效解析层。

模式是全局运行时态：持久化于 ``app_settings``（key=``model.runtime_mode``），
解析时叠加在 ``resolve_model_config``（DB 激活 Provider → env/YAML）之上，二者同层独立。
明文凭据不进入本模块；解析层永不 raise（应用库不可用回退 env 并诚实标注）。
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy.exc import SQLAlchemyError

from src.application.errors import ModelModePersistenceError
from src.application.model_providers import resolve_model_config
from src.application.transaction import in_transaction
from src.domain.model_runtime_mode import (
    MODEL_RUNTIME_MODE_KEY,
    ModelRuntimeMode,
    ModelRuntimeResolution,
)
from src.infrastructure.persistence.app_settings_repository import SqlAlchemyAppSettingsRepository
from src.infrastructure.persistence.database import SessionFactory

_MODE_VALUES: frozenset[str] = frozenset({"mock", "real"})

#: 应用库不可用/未迁移时的诚实降级标注，与"从未切换"区分。
_DB_UNAVAILABLE_REASON = "应用库不可用，回退环境变量决定"

#: real 模式但无可用 Provider/API Key 时的诚实标注。
_NO_USABLE_KEY_REASON = "无可用 Provider/API Key"


class ModelModeApplicationService:
    """模型运行时模式的读取与写入用例。"""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get_mode(self) -> ModelRuntimeMode | None:
        """读取持久化模式；从未切换或应用库不可用返回 None（由解析层兜底 env）。"""
        session = self._session_factory()
        try:
            value = SqlAlchemyAppSettingsRepository(session).get(MODEL_RUNTIME_MODE_KEY)
        finally:
            session.close()
        if value not in _MODE_VALUES:
            return None
        return value  # type: ignore[return-value]

    def set_mode(self, mode: ModelRuntimeMode) -> None:
        """持久化模式；写失败抛 ModelModePersistenceError，不产生半状态。"""
        try:
            in_transaction(
                self._session_factory,
                lambda session: SqlAlchemyAppSettingsRepository(session).set(MODEL_RUNTIME_MODE_KEY, mode),
            )
        except SQLAlchemyError as error:
            raise ModelModePersistenceError() from error


def resolve_runtime_mode(
    session_factory: SessionFactory,
    secret_key: bytes | None,
) -> ModelRuntimeResolution:
    """解析生效运行时模式；应用库不可用/未迁移时回退 env，永不 raise。

    返回 ``mode``（生效模式）、``mode_source``（runtime/env 诚实来源）、
    ``mode_available``（real 是否有可用 Key；mock 恒 True）、``mode_unavailable_reason``、
    以及供 LLM 构造/展示的生效 ``config``（``mode=mock`` 时 llm.api_key 强制为 ``"mock"``）。
    """
    config = resolve_model_config(session_factory, secret_key)
    if not isinstance(config.get("llm"), dict):
        config["llm"] = {}

    persisted_mode, db_available = _read_persisted_mode(session_factory)
    mode, mode_source = _resolve_mode_and_source(config, persisted_mode)
    if mode == "mock":
        config["llm"]["api_key"] = "mock"
    mode_available, reason = _resolve_availability(config, mode, persisted_mode, db_available)
    return ModelRuntimeResolution(
        mode=mode,
        mode_source=mode_source,
        mode_available=mode_available,
        mode_unavailable_reason=reason,
        config=config,
    )


def _read_persisted_mode(session_factory: SessionFactory) -> tuple[ModelRuntimeMode | None, bool]:
    """读取持久化模式；应用库不可用返回 (None, False)。"""
    try:
        session = session_factory()
        try:
            value = SqlAlchemyAppSettingsRepository(session).get(MODEL_RUNTIME_MODE_KEY)
        finally:
            session.close()
    except SQLAlchemyError:
        return None, False
    if value not in _MODE_VALUES:
        return None, True
    return value, True  # type: ignore[return-value]


def _resolve_mode_and_source(
    config: dict[str, dict[str, str]],
    persisted_mode: ModelRuntimeMode | None,
) -> tuple[ModelRuntimeMode, Literal["runtime", "env"]]:
    """运行时覆盖优先；从未切换时按 env 生效配置的 api_key 判定。"""
    if persisted_mode is not None:
        return persisted_mode, "runtime"
    api_key = config.get("llm", {}).get("api_key")
    return ("mock", "env") if (not api_key or api_key == "mock") else ("real", "env")


def _resolve_availability(
    config: dict[str, dict[str, str]],
    mode: ModelRuntimeMode,
    persisted_mode: ModelRuntimeMode | None,
    db_available: bool,
) -> tuple[bool, str | None]:
    """mock 恒可用；real 需要生效配置有真实 Key。应用库降级优先标注。"""
    if not db_available:
        return True, _DB_UNAVAILABLE_REASON
    if mode == "mock":
        return True, None
    api_key = config.get("llm", {}).get("api_key")
    if api_key and api_key != "mock":
        return True, None
    return False, _NO_USABLE_KEY_REASON
