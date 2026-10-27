"""主 Agent 严格预算：调用前扣记，超时取剩余预算与单次上限的较小值。"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from src.domain.main_agent import (
    MAX_AGENT_TOOL_CALLS,
    MAX_KNOWLEDGE_LOADS,
    MAX_MAIN_DECISIONS,
    MAX_MODEL_CALL_SECONDS,
    MAX_RUN_WALL_CLOCK_SECONDS,
    MAX_TOOL_WAIT_SECONDS,
)


@dataclass(frozen=True, slots=True)
class BudgetGrant:
    """一次被允许的调用：有效超时与是否被总预算压缩。"""

    effective_seconds: float
    clipped: bool


class MainAgentBudget:
    """一次 Run 的进程内预算；不跨 Run 复用，也不访问持久化。"""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall_clock_seconds: float = MAX_RUN_WALL_CLOCK_SECONDS,
        max_decisions: int = MAX_MAIN_DECISIONS,
        max_knowledge_loads: int = MAX_KNOWLEDGE_LOADS,
        max_tool_calls: int = MAX_AGENT_TOOL_CALLS,
    ) -> None:
        if wall_clock_seconds <= 0:
            raise ValueError("Run 总时间预算必须为正。")
        self._clock = clock
        self._deadline = clock() + wall_clock_seconds
        self._max_decisions = max_decisions
        self._max_knowledge_loads = max_knowledge_loads
        self._max_tool_calls = max_tool_calls
        self.decisions = 0
        self.knowledge_loads = 0
        self.tool_calls = 0

    def remaining(self) -> float:
        """返回总预算剩余秒数；已过期固定返回 0。"""
        return max(0.0, self._deadline - self._clock())

    def start_decision(self) -> BudgetGrant | None:
        """扣记一次模型决策；预算不足返回 None，调用方安全失败。"""
        if self.decisions >= self._max_decisions:
            return None
        remaining = self.remaining()
        if remaining <= 0:
            return None
        self.decisions += 1
        effective = min(MAX_MODEL_CALL_SECONDS, remaining)
        return BudgetGrant(effective_seconds=effective, clipped=remaining < MAX_MODEL_CALL_SECONDS)

    def can_load_knowledge(self) -> bool:
        """检查是否还能尝试装入知识；加载失败不消耗次数，成功后才记账。"""
        return self.knowledge_loads < self._max_knowledge_loads and self.remaining() > 0

    def record_knowledge_load(self) -> None:
        """记录一次成功装入；只由装入成功路径调用。"""
        if self.knowledge_loads >= self._max_knowledge_loads:
            raise ValueError("知识加载次数已耗尽。")
        self.knowledge_loads += 1

    def start_tool_call(self) -> BudgetGrant | None:
        """扣记一次工具调用；超限或总预算耗尽返回 None。"""
        if self.tool_calls >= self._max_tool_calls:
            return None
        remaining = self.remaining()
        if remaining <= 0:
            return None
        self.tool_calls += 1
        effective = min(MAX_TOOL_WAIT_SECONDS, remaining)
        return BudgetGrant(effective_seconds=effective, clipped=remaining < MAX_TOOL_WAIT_SECONDS)
