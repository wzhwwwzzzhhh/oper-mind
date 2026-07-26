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
