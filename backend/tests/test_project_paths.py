"""P1.1b 项目路径与配置加载测试。"""

from pathlib import Path

import yaml

from src import config
from src.memory.long_term import LongTermMemory
from src.project_paths import BACKEND_ROOT, CONFIG_DIR, DATA_DIR, PROJECT_ROOT


def test_project_paths_固定指向仓库根资源() -> None:
    """路径常量只由模块位置推导，不依赖 pytest 当前工作目录。"""
    assert BACKEND_ROOT == PROJECT_ROOT / "backend"
    assert CONFIG_DIR == PROJECT_ROOT / "config"
    assert DATA_DIR == PROJECT_ROOT / "data"
    assert (CONFIG_DIR / "config.example.yaml").is_file()


def test_load_config_从根配置目录读取并优先本地配置(monkeypatch, tmp_path) -> None:
    """本地配置优先于模板，目录来源由集中式 CONFIG_DIR 决定。"""
    local_config = {
        "llm": {
            "api_key": "local-key",
            "base_url": "http://local.example",
            "model": "local-model",
        }
    }
    example_config = {
        "llm": {
            "api_key": "example-key",
            "base_url": "http://example.invalid",
            "model": "example-model",
        }
    }
    (tmp_path / "config.local.yaml").write_text(
        yaml.safe_dump(local_config), encoding="utf-8"
    )
    (tmp_path / "config.example.yaml").write_text(
        yaml.safe_dump(example_config), encoding="utf-8"
    )
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)

    assert config._load_yaml_config() == local_config


def test_load_config_环境变量覆盖且保留_mock_fallback(monkeypatch) -> None:
    """环境变量优先于文件，并可显式配置确定性 mock 模式。"""
    monkeypatch.setattr(
        config,
        "_load_yaml_config",
        lambda: {
            "llm": {
                "api_key": "file-key",
                "base_url": "https://file.example",
                "model": "file-model",
            }
        },
    )
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")

    loaded = config.load_config()

    assert loaded["llm"] == {
        "api_key": "mock",
        "base_url": "http://mock",
        "model": "mock",
    }


def test_long_term_memory_默认写入根数据目录(monkeypatch) -> None:
    """长期记忆默认路径不再由调用时工作目录决定。"""
    monkeypatch.setattr(LongTermMemory, "load", lambda self: None)

    memory = LongTermMemory()

    assert memory.storage_path == DATA_DIR / "memory.json"
    assert isinstance(memory.storage_path, Path)
