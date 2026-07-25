"""真实评测配置测试 —— 诊断 LLM 与裁判 LLM 必须分离装配。"""

import pytest
import yaml

from src.config import load_config


def test_load_config_环境变量覆盖诊断和裁判模型(monkeypatch, tmp_path) -> None:
    """两套环境变量应分别覆盖 YAML 中的诊断模型与裁判模型配置。"""
    config_path = tmp_path / "config.local.yaml"
    config_path.write_text(
        """llm:\n  api_key: diagnosis-yaml\n  base_url: https://diagnosis.example\n  model: diagnosis-yaml-model\njudge_llm:\n  api_key: judge-yaml\n  base_url: https://judge.example\n  model: judge-yaml-model\n""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.config._load_yaml_config",
        lambda: yaml.safe_load(config_path.read_text(encoding="utf-8")),
    )
    monkeypatch.setenv("OPERMIND_API_KEY", "diagnosis-env")
    monkeypatch.setenv("OPERMIND_JUDGE_API_KEY", "judge-env")
    monkeypatch.setenv("OPERMIND_JUDGE_MODEL", "judge-env-model")

    config = load_config(require_judge_llm=True)

    assert config["llm"]["api_key"] == "diagnosis-env"
    assert config["judge_llm"]["api_key"] == "judge-env"
    assert config["judge_llm"]["model"] == "judge-env-model"


def test_load_config_真实评测缺少裁判配置时报错(monkeypatch) -> None:
    """真实诊断模型不能在未配置 judge_llm 时静默使用自身评分。"""
    monkeypatch.setattr(
        "src.config._load_yaml_config",
        lambda: {
            "llm": {
                "api_key": "diagnosis-key",
                "base_url": "https://diagnosis.example",
                "model": "diagnosis-model",
            }
        },
    )
    monkeypatch.delenv("OPERMIND_JUDGE_API_KEY", raising=False)
    monkeypatch.delenv("OPERMIND_JUDGE_BASE_URL", raising=False)
    monkeypatch.delenv("OPERMIND_JUDGE_MODEL", raising=False)

    with pytest.raises(ValueError, match="judge_llm"):
        load_config(require_judge_llm=True)


def test_config_hash_裁判模型变化生成不同指纹() -> None:
    """不同裁判模型对应不同评分条件，不能覆盖同一实验目录。"""
    from scripts.run_eval import _config_hash

    base = _config_hash("data/eval/cases.jsonl", 42, False, "diagnosis", "judge-a", "full", 1)
    changed = _config_hash("data/eval/cases.jsonl", 42, False, "diagnosis", "judge-b", "full", 1)

    assert base != changed


def test_config_hash_重复编号变化生成不同指纹() -> None:
    """同一实验组的不同 replicate 不能覆盖同一产物目录。"""
    from scripts.run_eval import _config_hash

    first = _config_hash("data/eval/cases.jsonl", 42, False, "diagnosis", "judge", "full", 1)
    second = _config_hash("data/eval/cases.jsonl", 42, False, "diagnosis", "judge", "full", 2)

    assert first != second
