"""LLM 调用封装"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from openai import OpenAI

from src.core.mock_runtime import infer_mock_role, mock_evidence_summary, plan_mock_tool
from src.domain.model_usage import UsageRecorder

LOGGER = logging.getLogger(__name__)


class LLMClient:
    """封装LLM API 调用，支持普通对话和 Function Calling"""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "qwen2.5:7b",
        default_temperature: float = 0.0,
        default_max_tokens: int | None = None,
        usage_recorder: UsageRecorder | None = None,
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        # 运行参数默认值：装配时从应用库配置解析注入，未配置时保持 0.0 / 不传。
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self.total_tokens = 0  # 累计 token 用量（真实调用累加，mock 恒为 0，供评测成本核算）
        # 用量采集端口：真实调用返回处落库；None=不采集（测试/旧入口保持现状）。
        self.usage_recorder = usage_recorder

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """
        调用LLM，返回完整响应。

        tools参数是FunctionCalling的工具定义列表。
        temperature=None 时用实例默认（默认 0.0，保证实验可复现，见 M3 复现性基础设施）；
        max_tokens=None 时用实例默认（默认不传，用模型自身限制）。
        """
        # Mock 模式：api_key 为 "mock" 时不调真实 API
        if self.client.api_key == "mock":
            return self._mock_chat(messages, tools)

        resolved_temperature = self.default_temperature if temperature is None else temperature
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": resolved_temperature,
        }
        if tools:
            kwargs["tools"] = tools
            # tool_choice="auto"让LLM自己决定是否调工具
            kwargs["tool_choice"] = "auto"
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        elif self.default_max_tokens is not None:
            kwargs["max_tokens"] = self.default_max_tokens

        try:
            # kwargs 是 SDK 参数的运行时子集，OpenAI stub 无法静态表达动态键组合；
            # SDK 自身会校验参数名，这里按受控边界 cast 到 Any。
            response = self.client.chat.completions.create(**cast(dict[str, Any], kwargs), timeout=60)
            message = response.choices[0].message

            # 累计 token 用量（供评测成本核算；usage 缺失时不计）
            usage = getattr(response, "usage", None)
            if usage is not None:
                self.total_tokens += getattr(usage, "total_tokens", 0) or 0

            # 用量落库采集（P8 副作用）：usage 缺失或 recorder 未注入时跳过；
            # 采集失败只记日志，绝不阻断或改变调用返回（AC8）。
            if self.usage_recorder is not None and usage is not None:
                self._record_usage(usage)

            # 把OpenAI的响应对象转成普通字典，方便后续处理
            result = {"role": "assistant", "content": message.content}

            if message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ]
            return  result
        except Exception as error:
            # 只记异常类型：异常文本可能带 base_url 或密钥片段。
            LOGGER.warning("LLM API 调用失败：%s", type(error).__name__)
            return {"role": "assistant", "content": "LLM API 调用失败", "error": "LLM_UNAVAILABLE"}

    def _record_usage(self, usage: Any) -> None:
        """把单次真实调用的用量写入应用库；失败降级为日志，不阻断调用。

        usage 为 OpenAI SDK 的 usage 对象（prompt_tokens / completion_tokens / total_tokens）。
        """
        recorder = self.usage_recorder
        if recorder is None:
            return
        try:
            input_tokens = getattr(usage, "prompt_tokens", 0) or 0
            output_tokens = getattr(usage, "completion_tokens", 0) or 0
            total_tokens = getattr(usage, "total_tokens", 0) or 0
            recorder.record(
                {
                    "model": self.model,
                    "input_tokens": int(input_tokens),
                    "output_tokens": int(output_tokens),
                    "total_tokens": int(total_tokens),
                    "occurred_at": datetime.now(UTC),
                }
            )
        except Exception as error:
            # 只记异常类型：不记录可能带凭据的异常文本。
            LOGGER.warning("用量采集失败（不影响本次调用）：%s", type(error).__name__)

    def _mock_chat(self, messages, tools):
        """按互斥角色工具菜单和显式场景事实返回确定性 mock 响应。"""

        role = infer_mock_role(tools)
        if tools and role is None:
            return {
                "role": "assistant",
                "content": "模拟场景：工具边界无法唯一识别，已失败关闭；暂无可用证据，当前结论未知。",
            }

        tool_messages = [message for message in messages if message.get("role") == "tool"]
        if tool_messages and role is not None:
            tool_name = _last_mock_tool_name(messages) or "unknown"
            return {
                "role": "assistant",
                "content": mock_evidence_summary(role, tool_name, str(tool_messages[-1].get("content", ""))),
            }

        # 获取最后一条用户消息
        last_msg = ""
        for m in reversed(messages):
            if m["role"] == "user":
                last_msg = m["content"]
                break

        if role is not None and tools:
            from data.scenarios import get_active_scenario

            call = plan_mock_tool(role, last_msg, tools, get_active_scenario())
            if call is not None:
                return {"role": "assistant", "content": None, "tool_calls": [call]}
            return {
                "role": "assistant",
                "content": "模拟场景：当前角色没有适用的显式场景事实；暂无可用证据，当前结论未知。",
            }

        # 默认回复
        return {
            "role": "assistant",
            "content": "模拟场景：当前没有可用的受控工具事实；暂无可用证据，当前结论未知。",
        }


def _last_mock_tool_name(messages: list[dict]) -> str | None:
    """从最近一次 assistant tool_calls 中提取工具名。"""
    for message in reversed(messages):
        calls = message.get("tool_calls")
        if not isinstance(calls, list) or not calls:
            continue
        function = calls[-1].get("function", {}) if isinstance(calls[-1], dict) else {}
        name = function.get("name") if isinstance(function, dict) else None
        return str(name) if name else None
    return None
