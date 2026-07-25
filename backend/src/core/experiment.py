"""M4 实验条件 —— 将实验组标签映射为确定的编排开关。"""

from dataclasses import dataclass
from typing import Literal


RoutingMode = Literal["adaptive", "single_agent", "force_chain", "force_parallel"]


@dataclass(frozen=True)
class ExperimentCondition:
    """单个实验组的编排条件。"""

    arm: str
    routing_mode: RoutingMode
    enable_debate: bool
    enable_reflection: bool


_EXPERIMENT_CONDITIONS: dict[str, ExperimentCondition] = {
    "single_agent": ExperimentCondition(
        arm="single_agent",
        routing_mode="single_agent",
        enable_debate=False,
        enable_reflection=True,
    ),
    "full": ExperimentCondition(
        arm="full",
        routing_mode="adaptive",
        enable_debate=True,
        enable_reflection=True,
    ),
    "no_debate": ExperimentCondition(
        arm="no_debate",
        routing_mode="adaptive",
        enable_debate=False,
        enable_reflection=True,
    ),
    "no_reflection": ExperimentCondition(
        arm="no_reflection",
        routing_mode="adaptive",
        enable_debate=True,
        enable_reflection=False,
    ),
    "force_chain": ExperimentCondition(
        arm="force_chain",
        routing_mode="force_chain",
        enable_debate=False,
        enable_reflection=True,
    ),
    "force_parallel": ExperimentCondition(
        arm="force_parallel",
        routing_mode="force_parallel",
        enable_debate=True,
        enable_reflection=True,
    ),
}


def get_experiment_condition(arm: str) -> ExperimentCondition:
    """返回实验组条件，不支持的标签直接报错。"""
    try:
        return _EXPERIMENT_CONDITIONS[arm]
    except KeyError as error:
        supported = "、".join(_EXPERIMENT_CONDITIONS)
        raise ValueError(f"不支持的实验组：{arm}，可选值：{supported}") from error


def supported_arms() -> tuple[str, ...]:
    """返回 CLI 可接受的实验组标签。"""
    return tuple(_EXPERIMENT_CONDITIONS)
