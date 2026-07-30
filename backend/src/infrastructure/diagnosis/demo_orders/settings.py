"""P4.1 订单慢查询靶场证据源的受控配置。"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from src.config import load_persistence_settings
from src.project_paths import PROJECT_ROOT


DEMO_ROOT = PROJECT_ROOT / "demo" / "orders-slow-query"
RUNTIME_ROOT = DEMO_ROOT / "runtime"
DEFAULT_LOG_FILE = RUNTIME_ROOT / "logs" / "order-service.jsonl"
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 5433
TARGET_DATABASE = "opermind_demo"
TARGET_SCHEMA = "opermind_demo"
TARGET_TABLE = "orders"
TARGET_INDEX = "idx_orders_user_created"
SERVICE_BASE_URL = "http://127.0.0.1:18080"


class DemoOrdersConfigurationError(ValueError):
    """靶场证据源配置不满足隔离约束时使用的内部错误。"""


class EvidenceMode(str, Enum):
    """P4.1 证据源装配模式。"""

    DISABLED = "disabled"
    MOCK = "mock"
    TARGET = "target"


class DemoOrdersEvidenceSettings(BaseModel):
    """仅允许访问固定订单慢查询靶场的配置。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: EvidenceMode = EvidenceMode.DISABLED
    database_host: str = TARGET_HOST
    database_port: int = TARGET_PORT
    database_name: str = TARGET_DATABASE
    database_user: str | None = None
    database_password: SecretStr | None = None
    service_base_url: str = SERVICE_BASE_URL
    log_file: Path = DEFAULT_LOG_FILE
    connection_timeout_seconds: int = Field(default=3, ge=1, le=10)
    query_timeout_milliseconds: int = Field(default=3000, ge=100, le=10000)
    log_line_limit: int = Field(default=500, ge=1, le=2000)

    @field_validator("database_host")
    @classmethod
    def validate_database_host(cls, value: str) -> str:
        """拒绝任何非本地隧道目标。"""
        if value != TARGET_HOST:
            raise ValueError("P4.1 仅允许固定本地 PostgreSQL 隧道。")
        return value

    @field_validator("database_port")
    @classmethod
    def validate_database_port(cls, value: int) -> int:
        """拒绝目标靶场之外的端口。"""
        if value != TARGET_PORT:
            raise ValueError("P4.1 仅允许固定 PostgreSQL 靶场端口。")
        return value

    @field_validator("database_name")
    @classmethod
    def validate_database_name(cls, value: str) -> str:
        """拒绝 gongkar 和所有非专用靶场库。"""
        if value != TARGET_DATABASE:
            raise ValueError("P4.1 仅允许专用 opermind_demo 数据库。")
        return value

    @field_validator("service_base_url")
    @classmethod
    def validate_service_base_url(cls, value: str) -> str:
        """服务读取只允许固定本地靶场 URL。"""
        if value.rstrip("/") != SERVICE_BASE_URL:
            raise ValueError("P4.1 仅允许固定订单服务靶场地址。")
        return SERVICE_BASE_URL

    @field_validator("log_file")
    @classmethod
    def validate_log_file(cls, value: Path) -> Path:
        """日志读取路径必须仍位于靶场运行目录内且为唯一日志文件。"""
        resolved = value.resolve()
        if not resolved.is_relative_to(RUNTIME_ROOT.resolve()) or resolved != DEFAULT_LOG_FILE.resolve():
            raise ValueError("P4.1 仅允许读取固定订单服务聚合日志。")
        return resolved

    @model_validator(mode="after")
    def validate_target_credentials(self) -> "DemoOrdersEvidenceSettings":
        """仅 target 模式要求显式靶场凭据。"""
        if self.mode is EvidenceMode.TARGET and (
            not self.database_user or self.database_password is None or not self.database_password.get_secret_value()
        ):
            raise ValueError("target 模式缺少专用靶场数据库凭据。")
        return self


def load_demo_orders_evidence_settings(
    environment: Mapping[str, str] | None = None,
    *,
    app_database_url: str | None = None,
) -> DemoOrdersEvidenceSettings:
    """从环境加载并校验 P4.1 靶场配置，绝不读取普通数据源配置。"""
    values = os.environ if environment is None else environment
    mode_text = values.get("OPERMIND_DEMO_ORDERS_EVIDENCE_MODE", EvidenceMode.DISABLED.value).strip().lower()
    try:
        mode = EvidenceMode(mode_text)
    except ValueError as error:
        raise DemoOrdersConfigurationError("订单慢查询证据模式不合法。") from error

    try:
        settings = DemoOrdersEvidenceSettings(
            mode=mode,
            database_host=values.get("OPERMIND_DEMO_PG_HOST", TARGET_HOST),
            database_port=_read_int(values, "OPERMIND_DEMO_PG_PORT", TARGET_PORT),
            database_name=values.get("OPERMIND_DEMO_PG_DATABASE", TARGET_DATABASE),
            database_user=values.get("OPERMIND_DEMO_PG_USER"),
            database_password=_secret_or_none(values.get("OPERMIND_DEMO_PG_PASSWORD")),
            service_base_url=values.get("OPERMIND_DEMO_ORDERS_SERVICE_URL", SERVICE_BASE_URL),
            log_file=Path(values.get("OPERMIND_DEMO_ORDERS_LOG_FILE", str(DEFAULT_LOG_FILE))),
        )
    except (TypeError, ValueError) as error:
        raise DemoOrdersConfigurationError("订单慢查询靶场配置不符合受控范围。") from error

    if settings.mode is EvidenceMode.TARGET:
        current_app_database_url = app_database_url or load_persistence_settings().database_url
        if _is_target_database_url(current_app_database_url):
            raise DemoOrdersConfigurationError("应用元数据库不得复用订单慢查询靶场。")
    return settings


def _read_int(values: Mapping[str, str], name: str, default: int) -> int:
    """读取整数环境变量，非法值会被上层收敛为安全配置错误。"""
    raw_value = values.get(name)
    return default if raw_value is None else int(raw_value)


def _secret_or_none(value: str | None) -> SecretStr | None:
    """避免把未提供的密码转换为空 SecretStr。"""
    return SecretStr(value) if value else None


def _is_target_database_url(database_url: str) -> bool:
    """只比较 URL 的地址边界，不展示或解析出任何凭据。"""
    try:
        url = make_url(database_url)
    except ArgumentError:
        return False
    if not url.drivername.startswith("postgresql"):
        return False
    return (
        url.host in {TARGET_HOST, "localhost", "::1"}
        and (url.port or 5432) == TARGET_PORT
        and url.database == TARGET_DATABASE
    )
