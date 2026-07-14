"""配置管理：从 YAML 文件加载基础配置，并允许环境变量覆盖 llm 配置"""

import yaml
import os


# 环境变量名 -> llm 配置字段名 的映射
# 环境变量优先级高于 yaml，用于把密钥等敏感信息从 yaml 中剥离
_ENV_TO_LLM_KEY = {
    "OPERMIND_API_KEY": "api_key",
    "OPERMIND_BASE_URL": "base_url",
    "OPERMIND_MODEL": "model",
}


def _load_yaml_config() -> dict:
    """
    从 yaml 文件加载基础配置。

    加载顺序：
    1. config/config.local.yaml（如果有）
    2. config/config.example.yaml（fallback）

    两个文件都不存在时返回空 dict（由调用方决定是否报错），
    这样即使没有 yaml，也能仅靠环境变量构造配置。
    """
    config_dir = os.path.join(os.path.dirname(__file__), "..", "config")

    # 候选文件按优先级排列：local 优先，example 兜底
    candidate_paths = [
        os.path.join(config_dir, "config.local.yaml"),
        os.path.join(config_dir, "config.example.yaml"),
    ]

    for path in candidate_paths:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                # 空文件时 safe_load 返回 None，统一成空 dict
                return yaml.safe_load(f) or {}

    return {}


def _apply_env_overrides(config: dict) -> dict:
    """
    用环境变量覆盖 llm 配置。

    只要对应环境变量存在，就优先采用其值（覆盖 yaml 中的同名字段）。
    环境变量缺失时保留 yaml 原值。
    """
    # 确保 llm 子配置存在，避免只有环境变量时缺少挂载点
    llm_config = config.setdefault("llm", {})

    for env_name, llm_key in _ENV_TO_LLM_KEY.items():
        env_value = os.environ.get(env_name)
        if env_value is not None:
            llm_config[llm_key] = env_value

    return config


def load_config() -> dict:
    """
    加载配置，返回结构为 { "llm": { "api_key", "base_url", "model" } }。

    加载策略：
    1. 先读 yaml 拿到基础配置（local 优先，example 兜底，缺失则为空）。
    2. 再用环境变量覆盖 llm 配置：
       OPERMIND_API_KEY / OPERMIND_BASE_URL / OPERMIND_MODEL。
    3. 只有当「yaml 缺失 且 环境变量里也没有 api_key」时才报错，
       以保证仅靠环境变量（含 mock 模式 OPERMIND_API_KEY=mock）也能正常运行。
    """
    config = _load_yaml_config()
    config = _apply_env_overrides(config)

    # 校验：必须能拿到 api_key，否则既没有 yaml 也没有环境变量，无法工作
    if not config.get("llm", {}).get("api_key"):
        config_dir = os.path.join(os.path.dirname(__file__), "..", "config")
        local_path = os.path.join(config_dir, "config.local.yaml")
        example_path = os.path.join(config_dir, "config.example.yaml")
        raise FileNotFoundError(
            "找不到可用配置！未提供 API Key。\n"
            "请使用以下任一方式配置：\n"
            f"  1. 创建 {local_path}（参考 {example_path}）\n"
            "  2. 设置环境变量 OPERMIND_API_KEY"
            "（可选 OPERMIND_BASE_URL、OPERMIND_MODEL；"
            "开发/测试可用 OPERMIND_API_KEY=mock）"
        )

    return config
