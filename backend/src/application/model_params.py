"""P8 模型运行参数应用服务与生效解析层。

参数是全局运行时态：持久化于 ``app_settings``（key=``model.params``，JSON），
与 ``model.runtime_mode`` 同层独立；解析层永不 raise（应用库不可用回退默认值并诚实标注）。
"""

from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError

from src.application.errors import ModelParamsPersistenceError
from src.application.transaction import in_transaction
from src.domain.model_params import (
    MODEL_PARAMS_KEY,
    ModelParams,
    ModelParamsResolution,
    decode_params,
    default_resolution,
    encode_params,
)
from src.infrastructure.persistence.app_settings_repository import SqlAlchemyAppSettingsRepository
from src.infrastructure.persistence.database import SessionFactory


class ModelParamsApplicationService:
    """模型运行参数的写入用例；持久化失败抛 ModelParamsPersistenceError，不产生半状态。"""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get(self) -> ModelParams:
        """读取已配置参数；未配置或应用库不可用时返回空参数（用默认值）。"""
        try:
            session = self._session_factory()
            try:
                raw = SqlAlchemyAppSettingsRepository(session).get(MODEL_PARAMS_KEY)
            finally:
                session.close()
        except SQLAlchemyError:
            return ModelParams()
        return decode_params(raw)

    def set(self, params: ModelParams) -> None:
        """全量替换已配置参数（null=清除该项）；写失败抛错误，不产生半状态。"""
        try:
            in_transaction(
                self._session_factory,
                lambda session: SqlAlchemyAppSettingsRepository(session).set(
                    MODEL_PARAMS_KEY, encode_params(params)
                ),
            )
        except SQLAlchemyError as error:
            raise ModelParamsPersistenceError() from error


def resolve_model_params(session_factory: SessionFactory) -> ModelParamsResolution:
    """解析生效模型运行参数；应用库不可用/未迁移时回退默认值，永不 raise。

    返回已配置值（未配置为 None）与后端默认值，供 LLM 构造点与
    ``GET /model/config`` 使用（诚实标注：未配置时用默认值）。
    """
    try:
        session = session_factory()
        try:
            raw = SqlAlchemyAppSettingsRepository(session).get(MODEL_PARAMS_KEY)
        finally:
            session.close()
    except SQLAlchemyError:
        return default_resolution()
    params = decode_params(raw)
    return ModelParamsResolution(
        temperature=params.temperature,
        max_tokens=params.max_tokens,
        temperature_default=default_resolution()["temperature_default"],
        max_tokens_default=default_resolution()["max_tokens_default"],
    )
