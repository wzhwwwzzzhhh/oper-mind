"""LLM 调用封装"""

from openai import OpenAI

class LLMClient:
    """封装LLM API 调用，支持普通对话和 Function Calling"""

    def __init__(self , api_key: str, base_url: str ,model: str = "qwen2.5:7b"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def chat(self,
             messages: list[dict],
             tools: list[dict] | None = None,
             temperature: float = 0.0,
    ) -> dict:
        """
        调用LLM，返回完整响应。

        tools参数是FunctionCalling的工具定义列表。
        temperature=0.0让LLM 输出确定，保证实验可复现（见 M3 复现性基础设施）。
        """
        # Mock 模式：api_key 为 "mock" 时不调真实 API
        if self.client.api_key == "mock":
            return self._mock_chat(messages, tools)

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            # tool_choice="auto"让LLM自己决定是否调工具
            kwargs["tool_choice"] = "auto"

        try:
            response = self.client.chat.completions.create(**kwargs,timeout=60)
            message = response.choices[0].message

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
        except Exception as e:
            print(f"LLM API 调用失败: {e}")
            return {"role": "assistant", "content": "LLM API 调用失败", "error": str(e)}

    def _mock_chat(self, messages, tools):
        """Mock LLM 返回，不需要 API Key"""
        import random

        # 检查是否已经执行过工具（有 tool 角色的消息）
        # 如果有，说明这是 ReAct 循环的第二轮以上，直接给最终答案
        has_tool_result = any(
            m.get("role") == "tool" for m in messages
        )
        if has_tool_result:
            return {
                "role": "assistant",
                "content": (
                    "【诊断结论】通过 EXPLAIN 分析发现该 SQL 存在全表扫描问题。\n"
                    "问题根因：status 字段没有索引导致全表扫描 50000 行。\n"
                    "优化建议：为 status 字段添加索引。\n"
                    "```sql\nALTER TABLE `orders` ADD INDEX `idx_status` (`status`);\n```\n"
                    "预期效果：访问类型从 ALL 变为 ref，扫描行数从 50000 降至约 8000。"
                ),
            }

        # 获取最后一条用户消息
        last_msg = ""
        for m in reversed(messages):
            if m["role"] == "user":
                last_msg = m["content"]
                break

        # 模拟工具调用：检查是否需要分析 SQL
        sql_keywords = ["select", "from", "where", "join", "order by", "group by"]
        is_sql = any(kw in last_msg.lower() for kw in sql_keywords)

        if is_sql and tools:
            # 模拟 LLM 调用 explain_sql
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_mock_1",
                        "type": "function",
                        "function": {
                            "name": "explain_sql",
                            "arguments": '{"sql": "' + last_msg.replace('"', '\\"') + '"}',
                        },
                    }
                ],
            }

        # 默认回复
        return {
            "role": "assistant",
            "content": f"Mock回复：收到了你的消息。如果是SQL诊断，请提供完整的SQL语句。",
        }

    def _mock_response(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """模拟 LLM 返回，测试 ReAct 循环时不需要真实 API Key"""
        last_msg = messages[-1]["content"] if messages else ""

        # 如果已经执行过工具，直接返回最终答案，不再继续调工具
        for m in reversed(messages):
            if m.get("role") == "tool":
                return {
                    "role": "assistant",
                    "content": "当前时间已返回，无需进一步操作。",
                }

        if tools and ("时间" in last_msg or "几" in last_msg):
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_mock",
                        "type": "function",
                        "function": {"name": "get_current_time", "arguments": "{}"},
                    }
                ],
            }

        return {
            "role": "assistant",
            "content": f"Mock回复: {last_msg[:50]}",
        }