# 03 手搓 ReAct 核心引擎

---

## 目标

从零手写 ReAct 循环 —— Agent 最核心的部分，不依赖任何框架。

---

## 前置依赖

- [ ] 01-环境搭建完成
- [ ] Python 够基础：函数、类、JSON、异常处理

---

## 核心概念

ReAct = **Rea**soning + **Act**ion（推理 + 行动），流程如下：

```
用户提问
  ↓
LLM 思考（Thought）→ 它决定下一步做什么
  ↓
LLM 返回两种可能之一：
  ① 最终答案 → 返回给用户，结束
  ② 调用工具（Action）→ 执行工具 → 得到观察结果（Observation）
  ↓
将观察结果发给 LLM → LLM 再思考 → 循环
```

代码核心就是一个 `while` 循环：

```
while 没到最大步数:
    response = llm.chat(messages)      # LLM 思考
    if response 是最终答案:
        return answer                   # 结束
    else:
        tool_result = run_tool(response) # 执行工具
        messages.append(tool_result)     # 把结果喂回去
```

---

## 步骤

### 第一步：创建 LLM 调用封装

文件：`src/core/llm.py`

```python
"""LLM 调用封装"""

from openai import OpenAI


class LLMClient:
    """封装 LLM API 调用，支持普通对话和 Function Calling"""

    def __init__(self, api_key: str, base_url: str, model: str = "deepseek-chat"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.1,
    ) -> dict:
        """
        调用 LLM，返回完整响应。

        tools 参数是 Function Calling 的工具定义列表。
        temperature=0.1 让 LLM 输出更确定，适合诊断场景。
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # Mock 模式：api_key 为 "mock" 时不调真实 API，方便开发测试
        if self.client.api_key == "mock":
            return self._mock_response(messages, tools)

        try:
            response = self.client.chat.completions.create(**kwargs, timeout=60)
            message = response.choices[0].message

            # 把 OpenAI 的响应对象转成普通字典，方便后续处理
            result = {"role": "assistant", "content": message.content}

            # 如果有工具调用，一起保存
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

            return result

        except Exception as e:
            print(f"[LLM Error] {e}")
            return {"role": "assistant", "content": None, "error": str(e)}

    def _mock_response(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """模拟 LLM 返回，测试 ReAct 循环时不需要真实 API Key"""
        last_msg = messages[-1]["content"] if messages else ""

        # 如果已经执行过工具，直接返回最终答案，不让 ReAct 死循环
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
```

**知识点：**

| 概念                   | 说明                                       |
| -------------------- | ---------------------------------------- |
| `tool_choice="auto"` | 让 LLM 自行决定是否调用工具。你也可以设 `"required"` 强制调用 |
| `temperature=0.1`    | 越低输出越确定。诊断场景不需要创造性，0.1 合适                |
| `tool_calls`         | LLM 返回的调用指令，告诉你要调哪个函数、传什么参数              |
| `timeout=60`         | Agent 一步可能较慢，给足 60 秒                     |

### 第二步：创建 Tool 注册中心

文件：`src/core/tool_registry.py`

```python
"""Tool 注册中心：管理所有可用的工具"""

import json


class Tool:
    """单个工具的定义"""

    def __init__(self, name: str, description: str, parameters: dict):
        """
        parameters 是 JSON Schema 格式，描述参数的类型和约束。

        示例：
        {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "要分析的SQL"}
            },
            "required": ["sql"]
        }
        """
        self.name = name
        self.description = description
        self.parameters = parameters

    def to_openai_schema(self) -> dict:
        """转换成 OpenAI Function Calling 要求的格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def execute(self, **kwargs) -> str:
        """子类重写此方法"""
        raise NotImplementedError("Tool must implement execute()")


class ToolRegistry:
    """工具注册中心"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        """注册一个工具"""
        self._tools[tool.name] = tool

    def get_schemas(self) -> list[dict]:
        """返回所有工具的 OpenAI Schema 列表，传给 LLM"""
        return [t.to_openai_schema() for t in self._tools.values()]

    def execute_tool(self, name: str, arguments: str) -> str:
        """
        执行指定工具。
        arguments 是 JSON 字符串，需要先解析。
        """
        if name not in self._tools:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)

        try:
            args = json.loads(arguments)
            result = self._tools[name].execute(**args)
            return str(result)
        except json.JSONDecodeError:
            return json.dumps({"error": "参数格式错误，无法解析"}, ensure_ascii=False)
        except TypeError as e:
            return json.dumps({"error": f"参数不匹配: {e}"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"执行异常: {e}"}, ensure_ascii=False)
```

**知识点：**

| 概念               | 说明                       |
| ---------------- | ------------------------ |
| JSON Schema      | 描述参数格式的规范。LLM 读这个来知道怎么传参 |
| `register()`     | 将工具注册到中心，LLM 才能发现它       |
| `execute_tool()` | 根据名字查找并执行，做好异常兜底         |

### 第三步：创建 ReAct Agent

文件：`src/core/agent.py`

```python
"""ReAct Agent 核心引擎"""

from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry


class Agent:
    """
    ReAct Agent 核心引擎。

    核心循环：
    1. 把消息发给 LLM
    2. 如果 LLM 返回最终答案 → 结束
    3. 如果 LLM 要调工具 → 执行 → 把结果加回消息 → 回到第1步
    """

    def __init__(self, llm: LLMClient, tools: ToolRegistry, system_prompt: str, max_steps: int = 10):
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]

    def run(self, user_input: str) -> str:
        """
        运行 Agent，处理用户输入，返回最终回答。
        """
        self.messages.append({"role": "user", "content": user_input})
        tool_schemas = self.tools.get_schemas()

        for step in range(self.max_steps):
            print(f"\n[Step {step + 1}/{self.max_steps}]")

            # 1. 调 LLM
            response = self.llm.chat(self.messages, tools=tool_schemas)
            self.messages.append(response)

            # 检查 LLM 是否报错
            if "error" in response:
                return f"LLM 调用失败: {response['error']}"

            # 2. 判断 LLM 返回了什么
            tool_calls = response.get("tool_calls")
            content = response.get("content")

            # 如果 LLM 要调工具
            if tool_calls:
                for tc in tool_calls:
                    func = tc["function"]
                    print(f"  → 调用工具: {func['name']}({func['arguments']})")

                    result = self.tools.execute_tool(func["name"], func["arguments"])
                    print(f"  ← 结果: {result[:100]}..." if len(result) > 100 else f"  ← 结果: {result}")

                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })

                # 继续循环，让 LLM 看到工具结果后决定下一步
                continue

            # 如果 LLM 直接回答了（没有调工具），这就是最终答案
            if content:
                return content

            # LLM 什么都没返回（极小概率），避免死循环
            return "Agent 没有生成有效响应"

        # 超过最大步数
        return f"Agent 超过最大步数 ({self.max_steps})，未得出最终结论"
```

**知识点：**

| 概念             | 说明                                        |
| -------------- | ----------------------------------------- |
| `max_steps`    | 最大循环步数，防止死循环。一般设 5-10                     |
| `tool_call_id` | 工具调用的唯一 ID，LLM 用它关联工具结果                   |
| `role: "tool"` | 工具执行结果的标识，LLM 读到 role="tool" 就知道这是之前调用的结果 |
| `continue`     | 继续下一轮循环，让 LLM 看到工具结果后处理                   |

### 第四步：创建主入口

文件：`src/main.py`

```python
"""CLI 入口"""
from datetime import datetime

from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry, Tool
from src.core.agent import Agent


class GetCurrentTimeTool(Tool):
    """获取当前时间的工具"""

    def __init__(self):
        super().__init__(
            name="get_current_time",
            description="获取当前时间和日期",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    def execute(self) -> str:
        return f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def build_agent(api_key: str = "mock") -> Agent:
    """构造 Agent 实例，所有依赖都注入进来"""
    llm = LLMClient(api_key=api_key, base_url="https://api.deepseek.com")

    tools = ToolRegistry()
    tools.register(GetCurrentTimeTool())

    system_prompt = """你是数据库诊断助手，帮助用户分析SQL性能和数据库问题。
请用专业的知识回答用户问题。
如果需要查询信息，可以使用提供的工具。"""

    return Agent(llm=llm, tools=tools, system_prompt=system_prompt)


def main():
    agent = build_agent()

    print("=" * 50)
    print("数据库诊断 Agent 已启动（输入 'exit' 退出）")
    print("=" * 50)

    while True:
        user_input = input("\n> ").strip()
        if user_input.lower() in ("exit", "quit", "q"):
            break

        result = agent.run(user_input)
        print(f"\n{result}")


if __name__ == "__main__":
    main()
```

---

## 运行验证

```bash
# 确保虚拟环境已激活
cd D:/market-handsome/newproject/db-agent
python src/main.py
```

然后输入：

```
> 现在几点了？
```

如果 Agent 调用 `get_current_time` 工具并返回时间，说明 ReAct 循环跑通了。

按 `exit` 退出。

---

## 验收标准

- [x] `python src/main.py` 能启动
- [x] 输入文字，Agent 有回复
- [x] 输入"现在几点了"，Agent 会调用 `get_current_time` 工具
- [x] 输入 `exit` 能退出

---

## Git 提交

```bash
git add .
git commit -m "feat: 实现ReAct核心引擎"
```

---

## 你会用到的知识点

| 概念               | 说明                                  |
| ---------------- | ----------------------------------- |
| ReAct 循环         | Thought → Action → Observation 反复循环 |
| Function Calling | LLM 返回结构化调用指令，你执行并回传结果              |
| Tool Registry    | 统一管理所有工具，LLM 通过注册表发现可用工具            |
| API Key Mock     | 开发时不用真实 Key，模拟 LLM 返回               |
| JSON Schema      | 描述工具参数的格式规范                         |

---

## 下阶段预告

当前 Agent 只做了一个示例工具。下一阶段：实现真正的数据库诊断 Tool（EXPLAIN / SHOW INDEX）。
