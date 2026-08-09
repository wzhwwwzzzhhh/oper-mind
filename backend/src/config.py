"""配置管理：从 YAML 文件加载基础配置，并允许环境变量覆盖模型配置。"""

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from src.project_paths import CONFIG_DIR, DATA_DIR

# 环境变量名 -> 配置段与字段名的映射。
# 环境变量优先级高于 YAML，用于把密钥等敏感信息从配置文件中剥离。
_ENV_TO_CONFIG_KEY = {
    "OPERMIND_API_KEY": ("llm", "api_key"),
    "OPERMIND_BASE_URL": ("llm", "base_url"),
    "OPERMIND_MODEL": ("llm", "model"),
    "OPERMIND_JUDGE_API_KEY": ("judge_llm", "api_key"),
    "OPERMIND_JUDGE_BASE_URL": ("judge_llm", "base_url"),
    "OPERMIND_JUDGE_MODEL": ("judge_llm", "model"),
    "OPERMIND_APP_DATABASE_URL": ("persistence", "database_url"),
    "OPERMIND_PG_DSN": ("services", "pg_dsn"),
    "OPERMIND_MONITOR_SAMPLE_INTERVAL_SECONDS": ("monitoring", "sample_interval_seconds"),
    "OPERMIND_MONITOR_RETENTION_HOURS": ("monitoring", "retention_hours"),
    "OPERMIND_MONITOR_QUERY_MAX_HOURS": ("monitoring", "query_max_hours"),
    "OPERMIND_HOST_METRICS_CACHE_SECONDS": ("host_metrics", "cache_seconds"),
    "OPERMIND_KNOWLEDGE_DIR": ("knowledge", "directory"),
}


def _load_yaml_config() -> dict:
    """从仓库根的本地或示例 YAML 加载基础配置。"""
    candidate_paths: list[Path] = [
        CONFIG_DIR / "config.local.yaml",
        CONFIG_DIR / "config.example.yaml",
    ]

    for path in candidate_paths:
        if path.exists():
            with path.open("r", encoding="utf-8") as file:
                return yaml.safe_load(file) or {}

    return {}


def _apply_env_overrides(config: dict) -> dict:
    """用环境变量覆盖诊断、裁判与应用数据库配置。"""
    for env_name, (section_name, field_name) in _ENV_TO_CONFIG_KEY.items():
        env_value = os.environ.get(env_name)
        if env_value is None:
            continue

        section = config.get(section_name)
        if not isinstance(section, dict):
            section = {}
            config[section_name] = section
        section[field_name] = env_value

    return config


def _require_llm_config(config: dict, section_name: str) -> None:
    """校验指定模型配置是否包含连接所需字段。"""
    section = config.get(section_name, {})
    missing_fields = [
        field_name
        for field_name in ("api_key", "base_url", "model")
        if not section.get(field_name)
    ]
    if not missing_fields:
        return

    fields = "、".join(missing_fields)
    raise ValueError(
        f"{section_name} 配置不完整，缺少：{fields}。"
        "请在 config.local.yaml 或对应 OPERMIND_* 环境变量中提供。"
    )


def load_config(require_judge_llm: bool = False) -> dict:
    """加载模型配置；真实评测可要求独立的裁判模型配置。"""
    config = _apply_env_overrides(_load_yaml_config())
    _require_llm_config(config, "llm")

    if require_judge_llm:
        _require_llm_config(config, "judge_llm")

    return config

DEFAULT_APP_DATABASE_URL = f"sqlite:///{(DATA_DIR / 'opermind.sqlite3').as_posix()}"


@dataclass(frozen=True)
class PersistenceSettings:
    """应用元数据数据库配置；不复用诊断数据源连接。"""

    database_url: str


def load_persistence_settings() -> PersistenceSettings:
    """加载应用数据库 URL，保留根目录 SQLite 开发默认值。"""
    config = _apply_env_overrides(_load_yaml_config())
    persistence = config.get("persistence") or {}
    database_url = persistence.get("database_url") or DEFAULT_APP_DATABASE_URL
    if not isinstance(database_url, str) or not database_url.strip():
        raise ValueError("persistence.database_url 必须是非空数据库 URL。")
    return PersistenceSettings(database_url=database_url)


@dataclass(frozen=True)
class ServiceSettings:
    """外部服务连接设置；缺省表示未配置。"""

    pg_dsn: str | None


def load_service_settings() -> ServiceSettings:
    """读取外部服务 DSN；未配置返回 None。只读环境变量，不打印/记录 dsn。"""
    config = _apply_env_overrides(_load_yaml_config())
    services = config.get("services") or {}
    dsn = services.get("pg_dsn")
    if not isinstance(dsn, str) or not dsn.strip():
        return ServiceSettings(pg_dsn=None)
    return ServiceSettings(pg_dsn=dsn)


def load_service_dsn(instance_id: str) -> str | None:
    """读取指定服务实例的命名空间 DSN；缺省时返回 None。"""
    env_name = f"OPERMIND_SERVICE_{instance_id.upper().replace('-', '_')}_DSN"
    dsn = os.environ.get(env_name)
    if isinstance(dsn, str) and dsn.strip():
        return dsn
    return None


def load_service_log_dir(instance_id: str) -> str | None:
    """读取指定服务实例的受管日志目录；缺省时返回 None。

    命名空间与 `load_service_dsn` 同构（`OPERMIND_SERVICE_<INSTANCE_ID>_LOG_DIR`），
    仅环境变量、零落库、不打印不记录。
    """
    env_name = f"OPERMIND_SERVICE_{instance_id.upper().replace('-', '_')}_LOG_DIR"
    value = os.environ.get(env_name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


@dataclass(frozen=True)
class KnowledgeSettings:
    """受管知识目录配置；未配置时不启用知识检索。"""

    directory: str | None


def load_knowledge_settings() -> KnowledgeSettings:
    """读取受管知识目录；环境变量优先于 YAML，未配置返回 None。"""
    config = _apply_env_overrides(_load_yaml_config())
    knowledge = config.get("knowledge") or {}
    directory = knowledge.get("directory")
    if not isinstance(directory, str) or not directory.strip():
        return KnowledgeSettings(directory=None)
    return KnowledgeSettings(directory=directory.strip())


def load_action_mode() -> str:
    """根据受控靶场 DSN 是否配置选择动作模式；默认保持 mock 空态。"""
    return "target" if load_service_dsn("postgres-target") is not None else "mock"


@dataclass(frozen=True)
class MonitorSettings:
    """历史监控采样与查询窗口配置。"""

    sample_interval_seconds: int = 300
    retention_hours: int = 24
    query_max_hours: int = 24


def load_monitor_settings() -> MonitorSettings:
    """读取并校验历史监控配置，环境变量优先于 YAML。"""
    config = _apply_env_overrides(_load_yaml_config())
    monitoring = config.get("monitoring") or {}
    values: dict[str, int] = {}
    for field_name, lower, upper, default in (
        ("sample_interval_seconds", 30, 86400, 300),
        ("retention_hours", 1, 168, 24),
        ("query_max_hours", 1, 168, 24),
    ):
        raw_value = monitoring.get(field_name, default)
        try:
            value = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"monitoring.{field_name} 必须是整数。") from exc
        if not lower <= value <= upper:
            raise ValueError(f"monitoring.{field_name} 必须在 {lower} 到 {upper} 范围内。")
        values[field_name] = value
    if values["query_max_hours"] > values["retention_hours"]:
        raise ValueError("monitoring.query_max_hours 不能超过 retention_hours。")
    return MonitorSettings(**values)


@dataclass(frozen=True)
class HostMetricsSettings:
    """主机指标采集缓存配置。"""

    cache_seconds: int = 10


def load_host_metrics_settings() -> HostMetricsSettings:
    """读取并校验主机指标缓存配置，环境变量优先于 YAML。"""
    config = _apply_env_overrides(_load_yaml_config())
    host_metrics = config.get("host_metrics") or {}
    raw_value = host_metrics.get("cache_seconds", 10)
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("host_metrics.cache_seconds 必须是整数。") from exc
    if not 0 <= value <= 600:
        raise ValueError("host_metrics.cache_seconds 必须在 0 到 600 范围内。")
    return HostMetricsSettings(cache_seconds=value)
