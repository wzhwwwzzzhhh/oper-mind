# 任务 P2-A：让 BaseAgent 的工具调用走 ToolGateway

## 背景（只读，不要照抄进代码）
`ToolGateway`(`backend/src/core/tool_gateway.py`)是"大脑调用工具的唯一受控入口"。
现在 `BaseAgent`(`backend/src/core/agent.py`)在 ReAct 循环里直接调
`self.tools.execute_tool(name, arguments)`,**绕过了网关**。本任务把这一步改成走网关,
并把每次调用的结构化审计记录收集起来,供后续（另一个任务）串进 Trace。

**本任务只做后端接线，不碰 Trace、不碰前端、不碰 graph.py / coordinator。**

## 只允许创建/修改这两个文件
1. 修改：`backend/src/core/agent.py`
2. 创建：`backend/tests/test_agent_gateway.py`

**严禁触碰其他任何文件**：不改 `tool_gateway.py`、`tool_registry.py`、`graph.py`、
`coordinator.py`、`db_agent.py` 等，不改依赖，不动 conftest。
若你认为被测代码有 bug，**不要修**，在测试里用 `# 疑似缺陷:` 注释标注。

## 被测/被用 API（照此调用，不要臆测）
- `from src.core.tool_gateway import ToolGateway, GatewayResult`
- 构造：`ToolGateway(registry, timeout_seconds=10.0)`，其中 `registry` 就是 `BaseAgent.self.tools`
- 调用：`gw.invoke(name: str, arguments: str) -> GatewayResult`
  - `GatewayResult.output: str` —— 脱敏后的工具输出（可安全喂回 LLM 和前端）
  - `GatewayResult.record: ToolInvocation` —— 结构化审计记录，字段：
    `tool: str`、`status: Literal["ok","rejected","timeout","error"]`、
    `started_at: str`、`duration_ms: int`、`detail: str`
- 释放：`gw.shutdown()` —— 网关内部有线程池，用完必须关

## agent.py 要做的改动（精确）

### 1. 顶部 import
加 `from src.core.tool_gateway import ToolGateway`。

### 2. `__init__` 里新增一个实例字段
在现有字段旁边加：
```python
self._tool_invocations: list = []   # 本次 run 的工具调用审计记录（供上层串入 Trace）
```
（类型标注可写 `list[ToolInvocation]`，需 import ToolInvocation；写 `list` 也接受。）

### 3. `run()` 开头重置
在现有 `self.thinking_log = []` 旁边，加 `self._tool_invocations = []`。

### 4. 用网关承载整个 ReAct 循环，并保证线程池释放
在 `run()` 内，创建一次网关承载整轮循环，用 `try/finally` 保证 `shutdown()`：
```python
gateway = ToolGateway(self.tools)
try:
    for step in range(self.max_steps):
        ...  # 原有循环体
finally:
    gateway.shutdown()
```
**为什么必须 finally**：按产品设计每次 Run 现造一套 Agent，若不关线程池会逐 Run 泄漏线程。

### 5. 替换那一行工具调用
把：
```python
result = self.tools.execute_tool(func["name"], func["arguments"])
```
改成：
```python
gw_result = gateway.invoke(func["name"], func["arguments"])
result = gw_result.output
self._tool_invocations.append(gw_result.record)
```
后续把 `result` 塞进 `short_term` 的 tool 消息、写 `thinking_log`、`print` 摘要的逻辑**保持不变**
（此时 `result` 已是脱敏后的输出，正好也让喂回 LLM 的内容是安全的）。

### 6. 新增一个 getter（跟现有 `get_thinking()` 并列，风格一致）
```python
def get_tool_invocations(self) -> list:
    """返回本次 run 收集到的工具调用审计记录（供编排层串入 Trace）。"""
    return self._tool_invocations
```

### 不要做的事
- 不要删 `tool_registry.execute_tool`（本轮它变死代码是预期的，留给后续 P5 收口）。
- 不要改工具调用之外的循环逻辑、记忆逻辑、路由逻辑。
- 不要新增 `print`。

## 测试文件 `backend/tests/test_agent_gateway.py` 要覆盖
用**自建假 LLM + 自建桩工具**驱动 `BaseAgent.run()`，不依赖真实 LLM / mock 数据源。

### 假 LLM 契约（照此实现）
`BaseAgent` 在循环里调用 `self.llm.chat(messages, tools=tool_schemas)`，期望返回 dict：
- 要触发工具调用：
  ```python
  {"role": "assistant", "content": None,
   "tool_calls": [{"id": "call_1", "type": "function",
                   "function": {"name": "<工具名>", "arguments": "<JSON字符串>"}}]}
  ```
- 要结束循环给最终答：`{"role": "assistant", "content": "最终诊断结论"}`
- 失败：dict 带 `"error"` 键

造一个假 LLM 类：第一次 `chat` 返回一个工具调用，第二次返回最终答（用调用计数切换）。
它还需要能被 `BaseAgent` 正常构造——看 `BaseAgent.__init__` 需要的 `llm` 用法，
最小实现一个有 `chat(self, messages, tools=None, **kwargs)` 方法的类即可。
构造 `BaseAgent` 时用 `enable_long_term_memory=False` 隔离长期记忆。

### 桩工具
继承 `src.core.tool_registry.Tool`，注册进一个 `ToolRegistry` 传给 `BaseAgent`。
至少要有一个正常回显工具，和一个返回敏感明文的工具（验证喂回内容已脱敏）。

### 必须覆盖的用例（每条一个测试函数，中文 docstring，真断言）
1. **正常工具调用被收集**：run 结束后 `agent.get_tool_invocations()` 长度 >= 1，
   且其中一条 `record.tool` == 被调用的桩工具名、`record.status == "ok"`。
2. **喂回 LLM 的工具结果已脱敏**：桩工具返回含 `password=hunter2` 或 `sk-abcdef123456`,
   断言最终喂进 `short_term`（或 agent 拿到的 `result`）里**不含原始明文**。
   实现方式：让假 LLM 在第二次调用时把收到的 messages 存下来，测试检查那批 messages 文本中无敏感明文；
   或让桩工具返回敏感串并断言不会原样出现在 `get_conversation_history()` 里。
3. **每次 run 前记录清零**:连续 `run()` 两次，第二次 `get_tool_invocations()`
   不包含第一次的记录（长度不累加）。
4. **无工具调用的 run 不产生记录**：假 LLM 第一次就返回最终答（无 tool_calls）→
   `get_tool_invocations()` 为空列表，且 run 正常返回该最终答文本。

## 验收
- `pytest tests/test_agent_gateway.py -q` 全绿。
- `pytest tests/test_tool_gateway.py -q` 仍全绿（没碰它，但确认没连带打破）。
- 不许 `assert True` 凑数；每条断言针对真实行为。
- `git status` 只应新增/修改上面允许的两个文件。

## 完成后
**不要 commit。** 停下并告诉我"P2-A 完成"，我会审 diff + 跑测试后自己提交。
