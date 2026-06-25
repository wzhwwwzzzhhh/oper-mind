"""配置管理：从 YAML 文件加载配置"""

import yaml
import os


def load_config() -> dict:
    """
    加载配置，优先加载本地配置。

    加载顺序：
    1. config/config.local.yaml（如果有）
    2. config/config.example.yaml（fallback）

    如果两个文件都不存在，报错。
    这样本地开发者只需要配 local 文件，只改自己要改的字段。
    """
    config_dir = os.path.join(os.path.dirname(__file__), "..", "config")

    # 先尝试加载 local
    local_path = os.path.join(config_dir, "config.local.yaml")
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    # fallback 到 example
    example_path = os.path.join(config_dir, "config.example.yaml")
    if os.path.exists(example_path):
        with open(example_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    raise FileNotFoundError(
        "找不到配置文件！\n"
        f"请创建 {local_path}\n"
        f"参考 {example_path} 填写你的 API Key"
    )