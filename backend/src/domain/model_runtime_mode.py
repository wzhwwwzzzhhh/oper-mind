"""P8 模型运行时模式领域模型。

模式是全局运行时态（非 Provider 属性）：``mock`` / ``real`` 二值；
未显式切换时由 env/YAML 兜底决定，切换后持久化到应用库并覆盖 env。
"""

from __future__ import annotations

from typing import Literal, TypedDict

ModelRuntimeMode = Literal["mock", "real"]

#: app_settings 中存储运行时模式的键。
MODEL_RUNTIME_MODE_KEY = "model.runtime_mode"


class ModelRuntimeResolution(TypedDict):
    """模式解析结果：生效模式、诚实来源、可用性标注与生效配置。

    ``config`` 与 ``resolve_model_config`` 同构（``llm`` 段生效；
    ``judge_llm`` 已收口为未启用，不再承载生效配置，issue #104）；
    ``mode=mock`` 时 llm.api_key 被强制为 ``"mock"``，供 LLM 构造点走确定性场景。
    """

    mode: ModelRuntimeMode
    mode_source: Literal["runtime", "env"]
    mode_available: bool
    mode_unavailable_reason: str | None
    config: dict[str, dict[str, str]]
