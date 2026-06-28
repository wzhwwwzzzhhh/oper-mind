# 08 FastAPI 包装与完整测试

---

## 目标

用 FastAPI 把 Agent 包装成 HTTP API，并提供完整的测试用例和量化评估。

---

## 前置依赖

- [ ] 03-手搓ReAct核心引擎完成（Agent能跑）
- [ ] 04-Tool系统与数据库诊断工具完成

---

## 知识点：FastAPI 只需要 5 行

```python
from fastapi import FastAPI

app = FastAPI()

@app.post("/chat")
def chat(query: str):
    return {"result": agent.run(query)}
```

就这么多。不需要学 FastAPI 的全部。

---

## 步骤

### 1. 创建 FastAPI 应用

文件：`src/app.py`

```python
"""FastAPI 包装：把 Agent 变成 HTTP API"""

import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry
from src.core.agent import Agent
from src.tools.db_tools import ExplainTool, ShowIndexTool, ShowCreateTableTool
from src.scenarios.db_diagnosis import SYSTEM_PROMPT
from src.core.fallback import RuleEngine
from src.config import load_config

# ===== 1. 创建 FastAPI 实例 =====

app = FastAPI(
    title="数据库诊断 Agent API",
    description="输入 SQL，Agent 自动诊断并给出优化建议",
    version="1.0.0",
)


# ===== 2. 定义请求/响应模型 =====

class ChatRequest(BaseModel):
    """请求体"""
    query: str
    use_llm: bool = True  # 允许调用方选择是否使用 LLM
    show_thinking: bool = False  # 是否显示思考过程


class ChatResponse(BaseModel):
    """响应体"""
    result: str
    thinking: list[str] | None = None  # 思考过程
    mode: str = "llm"  # "llm" 或 "fallback"


# ===== 3. 初始化 Agent（单例） =====

def create_agent():
    """创建 Agent 实例"""
    config = load_config()
    llm_config = config["llm"]

    llm = LLMClient(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model=llm_config.get("model", "deepseek-chat"),
    )

    tools = ToolRegistry()
    tools.register(ExplainTool())
    tools.register(ShowIndexTool())
    tools.register(ShowCreateTableTool())

    return Agent(llm=llm, tools=tools, system_prompt=SYSTEM_PROMPT)


agent = create_agent()
rule_engine = RuleEngine()


# ===== 4. 定义 API 接口 =====

@app.get("/")
def root():
    """根路径，返回 API 信息"""
    return {
        "name": "数据库诊断 Agent",
        "version": "1.0.0",
        "endpoints": {
            "POST /chat": "诊断 SQL",
            "GET /health": "健康检查",
            "GET /memory/stats": "记忆统计",
        },
    }


@app.get("/health")
def health():
    """健康检查"""
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    诊断 SQL。

    请求体：
    ```json
    {
        "query": "SELECT * FROM orders WHERE status = 'PENDING'",
        "use_llm": true,
        "show_thinking": true
    }
    ```
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")

    if not request.use_llm:
        # 降级模式：使用规则引擎
        result = rule_engine.diagnose(request.query)
        return ChatResponse(result=result, mode="fallback")

    # LLM 模式
    result = agent.run(request.query)

    thinking = agent.get_thinking() if request.show_thinking else None
    return ChatResponse(result=result, thinking=thinking, mode="llm")


@app.get("/memory/stats")
def memory_stats():
    """查看记忆系统统计"""
    stats = agent.get_memory_stats()
    history = agent.long_term.get_recent(5)
    return {
        "stats": stats,
        "recent_records": history,
    }


@app.post("/memory/clear")
def clear_memory():
    """清空当前对话记忆"""
    agent.short_term.clear()
    return {"status": "ok", "message": "对话记忆已清空"}
```

### 2. 修改 LLMClient 支持 mock

> ⚠️ 如果你在 Phase 03 已经添加了 `_mock_response` 方法，现在把它**替换**成下面的 `_mock_chat`。
> Phase 03 的 `_mock_response` 只支持简单的 get_current_time 工具调用，
> 而 `_mock_chat` 能正确处理 Phase 04 添加的数据库诊断工具。

为了让 API 不需要真实 Key 也能测试，修改 `src/core/llm.py`：

在 `chat` 方法开头添加 mock 判断：

```python
def chat(self, messages, tools=None, temperature=0.1):
    # Mock 模式
    if self.client.api_key == "mock":
        return self._mock_chat(messages, tools)

    # 真实调用（原有代码）
    ...
```

添加 `_mock_chat` 方法（替换原有的 `_mock_response`）：

> **注意**：Mock 需要能模拟多轮 ReAct 循环——第一次返回 tool_call 调 EXPLAIN，
> 第二次看到 EXPLAIN 结果后返回最终诊断。否则 Agent 会一直调工具直到 max_steps 报错。

```python
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
```

### 3. 修改 Agent 支持思考过程追踪

文件：`src/core/agent.py`，需要在 `__init__`、`run` 方法中添加日志记录，并新增 `get_thinking` 方法。

在 `__init__` 方法末尾添加：
```python
self.thinking_log: list[str] = []
```

在 `run` 方法的 `self.current_query = user_input` 之后添加：
```python
self.thinking_log = []  # 清空上一次的思考记录
```

在 `run` 方法的 `if tool_calls:` 块中，把原来的 `print` 替换为同时记录日志：
```python
if tool_calls:
    for tc in tool_calls:
        func = tc["function"]
        step_log = f"Step {step + 1}: 调用 {func['name']}({func['arguments']})"
        print(f"→ {step_log}")

        result = self.tools.execute_tool(func["name"], func["arguments"])
        short_result = result[:100] + "..." if len(result) > 100 else result
        print(f"← {short_result}")
        self.thinking_log.append(f"{step_log} → {short_result}")

        tool_message = { ... }  # 原有代码不变
```

在 `run` 方法的 `if content:` 块中，在 `return content` 之前添加：
```python
self.thinking_log.append(f"最终回答: {content[:100]}...")
```

在类末尾添加 `get_thinking` 方法：
```python
def get_thinking(self) -> list[str]:
    return self.thinking_log
```

### 4. 运行 FastAPI

```bash
# 确保在虚拟环境中
cd D:/market-handsome/newproject/db-agent

# 启动服务
uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```

然后访问 http://localhost:8000/docs 可以看到自动生成的 Swagger 文档。

### 5. 测试 API

在另一个终端中测试：

```bash
# 健康检查
curl http://localhost:8000/health

# SQL 诊断（LLM 模式）
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT * FROM orders WHERE status = '\''PENDING'\''", "show_thinking": true}'

# SQL 诊断（降级模式）
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "SELECT * FROM orders WHERE status = '\''PENDING'\''", "use_llm": false}'
```

---

## 测试用例

创建文件 `data/test_cases.json`：

```json
[
  {
    "id": 1,
    "sql": "SELECT * FROM orders WHERE status = 'PENDING'",
    "category": "全表扫描",
    "expected_diagnosis": "缺少索引",
    "expected_tools": ["explain_sql", "show_create_table", "show_index"]
  },
  {
    "id": 2,
    "sql": "SELECT * FROM orders ORDER BY create_time DESC",
    "category": "文件排序",
    "expected_diagnosis": "缺少排序索引",
    "expected_tools": ["explain_sql", "show_create_table"]
  },
  {
    "id": 3,
    "sql": "SELECT o.* FROM orders o JOIN order_items i ON o.id = i.order_id WHERE i.product_id = 123",
    "category": "JOIN优化",
    "expected_diagnosis": "被驱动表缺少索引",
    "expected_tools": ["explain_sql", "show_create_table", "show_index"]
  },
  {
    "id": 4,
    "sql": "SELECT YEAR(create_time) FROM orders WHERE id = 1",
    "category": "索引失效",
    "expected_diagnosis": "函数包裹导致索引失效",
    "expected_tools": ["explain_sql"]
  },
  {
    "id": 5,
    "sql": "SELECT * FROM orders WHERE status = 'COMPLETED' AND create_time > '2024-01-01'",
    "category": "复合索引",
    "expected_diagnosis": "需要复合索引",
    "expected_tools": ["explain_sql", "show_create_table", "show_index"]
  },
  {
    "id": 6,
    "sql": "SELECT id, order_no FROM orders WHERE id = 1",
    "category": "索引正常",
    "expected_diagnosis": "性能良好",
    "expected_tools": ["explain_sql"]
  },
  {
    "id": 7,
    "sql": "DELETE FROM orders WHERE status = 'EXPIRED'",
    "category": "高危操作",
    "expected_diagnosis": "需要审批",
    "expected_tools": []
  }
]
```

### 运行测试

文件：`tests/test_diagnosis.py`

```python
"""自动化测试：验证 Agent 的诊断能力"""

import json
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.fallback import RuleEngine


def load_test_cases():
    """加载测试用例"""
    with open("data/test_cases.json", "r", encoding="utf-8") as f:
        return json.load(f)


def test_fallback_engine():
    """测试规则引擎的诊断能力"""
    cases = load_test_cases()
    engine = RuleEngine()

    passed = 0
    total = len(cases)

    print("=" * 60)
    print("规则引擎测试报告")
    print("=" * 60)

    for case in cases:
        sql = case["sql"]
        category = case["category"]

        result = engine.diagnose(sql)
        has_diagnosis = len(result) > 20
        is_pass = has_diagnosis

        status = "✅" if is_pass else "❌"
        print(f"\n{status} [{category}] {sql[:60]}...")
        print(f"   诊断结果: {'有输出' if has_diagnosis else '无输出'}")

        if is_pass:
            passed += 1

    print(f"\n{'=' * 60}")
    print(f"总计: {total} | 通过: {passed} | 失败: {total - passed}")
    print(f"通过率: {passed / total * 100:.1f}%")
    print(f"{'=' * 60}")

    return passed == total


if __name__ == "__main__":
    success = test_fallback_engine()
    sys.exit(0 if success else 1)
```

运行测试：

```bash
python tests/test_diagnosis.py
```

---

## 验收标准

- [ ] `uvicorn src.app:app --reload` 启动成功
- [ ] `GET /health` 返回 `{"status": "ok"}`
- [ ] `POST /chat` 能正常响应
- [ ] 降级模式（`use_llm: false`）不需要 API Key 也能工作
- [ ] `python tests/test_diagnosis.py` 测试通过

---

## Git 提交

```bash
git add .
git commit -m "feat: FastAPI包装与完整测试"
```

---

## 知识点总结

| 概念                 | 说明                            |
| ------------------ | ----------------------------- |
| FastAPI            | 高性能 Python Web 框架，自动生成 API 文档 |
| Pydantic BaseModel | 定义请求/响应数据结构，自动校验              |
| uvicorn            | ASGI 服务器，运行 FastAPI           |
| Swagger UI         | FastAPI 自动生成的 API 文档页面        |

---

## 下阶段预告

最后一阶段：整理 README + 准备面试话术。
