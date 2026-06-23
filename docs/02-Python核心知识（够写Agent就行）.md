# 02 Python 核心知识（够写 Agent 就行）

---

## 目标

掌握写 Agent 项目需要的 Python 知识，只学用得上的，不学的浪费时间的。

---

## 1. 变量与类型

Python 不用声明类型，但可以用类型注解（推荐，代码更清晰）。

```python
# 基本类型
name: str = "数据库诊断Agent"
version: int = 1
price: float = 9.99
is_active: bool = True

# 集合类型
tags: list[str] = ["慢SQL", "索引", "死锁"]
config: dict[str, any] = {"model": "deepseek", "temperature": 0.7}
```

**你要记住**：`list` 是有序列表，`dict` 是键值对，你会天天用。

---

## 2. 函数定义（你会写最多的东西）

```python
# 基础函数
def greet(name: str) -> str:
    return f"你好, {name}"

# 可选参数 + 默认值
def query(sql: str, limit: int = 10) -> list:
    return [{"id": 1}]

# 多个返回值（实际返回元组）
def parse_sql(sql: str) -> tuple[str, str]:
    table = "orders"
    condition = "status = 'PENDING'"
    return table, condition

# 调用
table_name, where_clause = parse_sql("SELECT * FROM orders WHERE status = 'PENDING'")
```

**知识点**：`-> str` 表示这个函数返回字符串。Python 不强制类型检查，但写了代码更可读。

---

## 3. 类（你的 Tool 和 Agent 会用）

```python
class Tool:
    """一个工具的基类"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
    
    def execute(self, **kwargs) -> str:
        """子类重写这个方法"""
        raise NotImplementedError

# 继承
class ExplainTool(Tool):
    def __init__(self):
        super().__init__("explain_sql", "执行 EXPLAIN 分析 SQL")
    
    def execute(self, sql: str) -> str:
        return f"执行计划结果: {sql}"
```

**知识点**：
- `__init__` 是构造函数，创建对象时自动调用
- `self` 代表实例本身，类内方法第一个参数永远是 self
- `raise NotImplementedError` 表示"子类必须自己实现"

---

## 4. JSON 处理（和 LLM 通信的核心）

```python
import json

# Python 字典 → JSON 字符串
tool_def = {
    "name": "explain_sql",
    "parameters": {
        "type": "object",
        "properties": {
            "sql": {"type": "string"}
        }
    }
}
json_str = json.dumps(tool_def, ensure_ascii=False, indent=2)  # 生成格式化JSON
print(json_str)

# JSON 字符串 → Python 字典
response = '{"sql": "SELECT * FROM orders", "time_ms": 12}'
data = json.loads(response)
print(data["sql"])  # SELECT * FROM orders
```

**知识点**：
- `json.dumps()` = dict → string（序列化）
- `json.loads()` = string → dict（反序列化）
- `ensure_ascii=False` 让中文不乱码
- 你和 LLM 之间永远在用 JSON 通信，这个必须熟练

---

## 5. HTTP 请求（调 LLM API）

```python
import httpx  # 比 requests 更现代，支持异步

# 同步调用
def call_llm(messages: list) -> str:
    response = httpx.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": "Bearer YOUR_KEY"},
        json={
            "model": "deepseek-chat",
            "messages": messages,
            "tools": []  # 你的 tool 定义
        },
        timeout=30
    )
    response.raise_for_status()  # 非200状态码会抛异常
    return response.json()  # 返回解析好的字典
```

但实际项目中你一般用 OpenAI SDK，不需要手撸 HTTP：

```python
from openai import OpenAI

client = OpenAI(
    api_key="YOUR_KEY",
    base_url="https://api.deepseek.com"  # DeepSeek 兼容 OpenAI
)

response = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "你好"}]
)
print(response.choices[0].message.content)
```

**我们项目里用 SDK 方式**。

---

## 6. 异常处理（LLM 经常抽风）

```python
def safe_call_llm(messages: list) -> str | None:
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            timeout=30
        )
        return response.choices[0].message.content
    except httpx.TimeoutException:
        print("LLM 超时")
        return None
    except Exception as e:
        print(f"LLM 调用失败: {e}")
        return None
```

**知识点**：`try/except` 捕获异常。你的 Agent 每步都必须有异常处理。

---

## 7. 列表推导式（写起来很爽）

```python
# 传统写法
result = []
for i in range(10):
    result.append(i * 2)

# 列表推导式（一行搞定）
result = [i * 2 for i in range(10)]

# 遍历字典
tools = [t.name for t in tool_list]  # ["explain", "index"]
```

---

## 8. if __name__ 的写法

```python
# main.py
from src.core.agent import Agent

def main():
    agent = Agent()
    result = agent.run("帮我分析: SELECT * FROM orders")
    print(result)

if __name__ == "__main__":
    main()
```

**知识点**：`if __name__ == "__main__"` 的意思是"这个文件被直接运行时执行下面的代码"。如果被别的文件 import 则不执行。

---

## 9. async/await（FastAPI 会用，简单了解）

```python
import asyncio

async def fetch_data():
    await asyncio.sleep(1)  # 模拟IO等待
    return "数据"

# 运行 async 函数
result = asyncio.run(fetch_data())
print(result)
```

**现阶段不用深入理解**，FastAPI 阶段自然就懂了。

---

## 你的速成路径

| 优先级 | 概念 | 什么时候用 |
|--------|------|-----------|
| ⭐⭐⭐ | 函数定义 + 类型注解 | 每天，每一行代码 |
| ⭐⭐⭐ | JSON 处理 | 和 LLM 通信时 |
| ⭐⭐⭐ | 类 + 继承 | 定义 Tool 时 |
| ⭐⭐⭐ | try/except | Agent 每一步都需要 |
| ⭐⭐ | HTTP 请求 / SDK | 调 LLM API 时 |
| ⭐⭐ | if __name__ | 写入口文件时 |
| ⭐ | async/await | FastAPI 阶段 |

---

## 你必须记住的（写多了自然记住，先收藏）

```python
import json
from openai import OpenAI

# 你每天都会敲这3行
client = OpenAI(api_key="xxx", base_url="xxx")
data = json.loads(json_str)
json_str = json.dumps(data, ensure_ascii=False, indent=2)
```

**这些就够你写 Agent 了。** 遇到不会的语法，查文档或问 AI，不需要提前全学完。
