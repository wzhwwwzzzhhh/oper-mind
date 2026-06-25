# 04 Tool 系统与数据库诊断工具

---

## 目标

实现完整的 Tool 系统，并创建慢 SQL 诊断的核心工具（EXPLAIN / SHOW INDEX / SHOW CREATE TABLE），配合 Mock 数据验证。

---

## 前置依赖

- [x] 03-手搓ReAct核心引擎完成（Agent引擎能跑起来）

---

## 知识点：Tool 系统架构

```
LLM 决定调哪个 Tool
  ↓
ToolRegistry 根据名字查找
  ↓
执行 Tool 的 execute() 方法
  ↓
返回结果字符串 → 喂回 LLM
```

**设计原则：**

1. **确定性逻辑在 Tool 里，决策权在 LLM 手里**
2. Tool 只做"执行并返回结果"，不做"判断"
3. 一个 Tool 只做一件事，职责单一

---

## 步骤

### 1. 创建数据库 Mock 数据

文件：`data/mock_db.py`

```python
"""模拟数据库返回结果，开发时不需要连真实数据库"""

import json

# 表结构定义（模拟 MySQL）
TABLES = {
    "orders": {
        "create_table": """
CREATE TABLE `orders` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `user_id` bigint(20) NOT NULL,
  `order_no` varchar(32) NOT NULL,
  `status` varchar(16) NOT NULL DEFAULT 'PENDING',
  `total_amount` decimal(10,2) NOT NULL,
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `pay_time` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """.strip(),
        "indexes": [
            {"Key_name": "PRIMARY", "Column_name": "id", "Seq_in_index": 1, "Non_unique": 0, "Cardinality": 50000},
            {"Key_name": "idx_user_id", "Column_name": "user_id", "Seq_in_index": 1, "Non_unique": 1, "Cardinality": 10000},
        ],
    },
    "order_items": {
        "create_table": """
CREATE TABLE `order_items` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `order_id` bigint(20) NOT NULL,
  `product_id` bigint(20) NOT NULL,
  `product_name` varchar(128) NOT NULL,
  `quantity` int(11) NOT NULL,
  `price` decimal(10,2) NOT NULL,
  PRIMARY KEY (`id`),
  KEY `idx_order_id` (`order_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """.strip(),
        "indexes": [
            {"Key_name": "PRIMARY", "Column_name": "id", "Seq_in_index": 1, "Non_unique": 0, "Cardinality": 200000},
            {"Key_name": "idx_order_id", "Column_name": "order_id", "Seq_in_index": 1, "Non_unique": 1, "Cardinality": 50000},
        ],
    },
    "products": {
        "create_table": """
CREATE TABLE `products` (
  `id` bigint(20) NOT NULL AUTO_INCREMENT,
  `name` varchar(128) NOT NULL,
  `category_id` bigint(20) NOT NULL,
  `price` decimal(10,2) NOT NULL,
  `stock` int(11) NOT NULL,
  `status` tinyint(4) NOT NULL DEFAULT 1,
  `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """.strip(),
        "indexes": [
            {"Key_name": "PRIMARY", "Column_name": "id", "Seq_in_index": 1, "Non_unique": 0, "Cardinality": 10000},
        ],
    },
}


def get_create_table(table_name: str) -> str | None:
    """返回建表语句"""
    table = TABLES.get(table_name)
    if table:
        return table["create_table"]
    return None


def get_indexes(table_name: str) -> list[dict] | None:
    """返回表的索引信息（SHOW INDEX FROM 的结果）"""
    table = TABLES.get(table_name)
    if table:
        return table["indexes"]
    return None


def explain_sql(sql: str) -> dict:
    """
    模拟 EXPLAIN 返回结果。
    根据 SQL 特征匹配已知的慢查询模式。
    """
    sql_upper = sql.upper()

    # 模式1：WHERE status = 'PENDING' 没索引
    if "STATUS" in sql_upper and "PENDING" in sql_upper:
        return {
            "id": 1,
            "select_type": "SIMPLE",
            "table": "orders",
            "type": "ALL",           # 全表扫描！
            "possible_keys": None,   # 没有可用索引
            "key": None,             # 实际没走索引
            "rows": 50000,
            "Extra": "Using where",
        }

    # 模式2：YEAR(create_time) 函数包裹导致索引失效
    if "YEAR" in sql_upper and "CREATE_TIME" in sql_upper:
        return {
            "id": 1,
            "select_type": "SIMPLE",
            "table": "orders",
            "type": "ALL",
            "possible_keys": "idx_create_time",
            "key": None,             # 函数包裹导致索引失效
            "rows": 50000,
            "Extra": "Using where; Using index",  # 提示用了索引但其实是全扫
        }

    # 模式3：ORDER BY create_time DESC 没索引
    if "ORDER BY" in sql_upper and "CREATE_TIME" in sql_upper:
        return {
            "id": 1,
            "select_type": "SIMPLE",
            "table": "orders",
            "type": "ALL",
            "possible_keys": None,
            "key": None,
            "rows": 50000,
            "Extra": "Using filesort",  # 文件排序，性能杀手！
        }

    # 模式4：JOIN 没索引
    if "JOIN" in sql_upper and "PRODUCT_ID" in sql_upper:
        return {
            "id": 1,
            "select_type": "SIMPLE",
            "table": "order_items",
            "type": "ALL",
            "possible_keys": None,
            "key": None,
            "rows": 200000,
            "Extra": "Using where",
        }

    # 模式5：复合查询，索引不全
    if "STATUS" in sql_upper and "COMPLETED" in sql_upper and "CREATE_TIME" in sql_upper:
        return {
            "id": 1,
            "select_type": "SIMPLE",
            "table": "orders",
            "type": "ref",
            "possible_keys": "idx_status",
            "key": "idx_status",
            "rows": 8000,
            "Extra": "Using where; Using filesort",
        }

    # 默认：性能良好
    return {
        "id": 1,
        "select_type": "SIMPLE",
        "table": "(unknown)",
        "type": "ref",
        "possible_keys": "PRIMARY",
        "key": "PRIMARY",
        "rows": 10,
        "Extra": "Using index",
    }


def extract_table_name(sql: str) -> str | None:
    """从 SQL 中提取表名（简单实现，只处理 SELECT FROM 场景）"""
    sql_upper = sql.upper()
    try:
        # 找 FROM 后面的表名
        idx = sql_upper.index("FROM") + 4
        rest = sql[idx:].strip()

        # 处理别名（FROM orders o 或 FROM orders AS o）
        parts = rest.split()
        table_name = parts[0].strip("`;,'\"")
        return table_name
    except (ValueError, IndexError):
        return None
```

**知识点：**

| 概念              | 说明                                 |
| --------------- | ---------------------------------- |
| Mock 数据         | 开发时模拟真实数据，不依赖外部系统                  |
| EXPLAIN type 字段 | `ALL`=全表扫描，`ref`=普通索引，`const`=唯一索引 |
| Using filesort  | MySQL 无法用索引排序，额外排序操作，大数据量极慢        |
| Cardinality     | 索引的区分度，值越大越好，太小说明这个索引意义不大          |

### 2. 创建数据库诊断 Tool

文件：`src/tools/db_tools.py`

```python
"""数据库诊断相关的 Tool"""

import json
from src.core.tool_registry import Tool


class ExplainTool(Tool):
    """执行 EXPLAIN 分析 SQL"""

    def __init__(self):
        super().__init__(
            name="explain_sql",
            description="执行 EXPLAIN 分析 SQL 的执行计划，返回访问类型、扫描行数、索引使用情况",
            parameters={
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "要分析的 SQL 语句，如 SELECT * FROM orders WHERE id = 1",
                    }
                },
                "required": ["sql"],
            },
        )

    def execute(self, sql: str) -> str:
        """执行 EXPLAIN 并返回格式化的结果"""
        from data.mock_db import explain_sql, extract_table_name

        plan = explain_sql(sql)
        table_name = extract_table_name(sql)

        result = f"EXPLAIN {table_name or '(unknown)'}:\n"
        result += f"  查询类型: {plan['select_type']}\n"
        result += f"  访问类型: {plan['type']}\n"
        result += f"  可能索引: {plan['possible_keys']}\n"
        result += f"  实际索引: {plan['key']}\n"
        result += f"  扫描行数: {plan['rows']}\n"
        result += f"  额外信息: {plan['Extra']}\n"

        # 附带简要解读
        warnings = []
        if plan["type"] == "ALL":
            warnings.append("⚠️ 全表扫描，性能风险高")
        if plan["Extra"] and "filesort" in plan["Extra"].lower():
            warnings.append("⚠️ 文件排序，数据量大时性能差")
        if plan["key"] is None and plan["possible_keys"]:
            warnings.append(f"⚠️ 有可用索引但没使用，可能是函数包裹或类型转换导致")
        if warnings:
            result += "\n" + "\n".join(warnings)

        return result


class ShowIndexTool(Tool):
    """查询表的索引信息"""

    def __init__(self):
        super().__init__(
            name="show_index",
            description="查询指定表的索引信息，返回索引名称、列名、唯一性、基数等",
            parameters={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "表名，如 orders、order_items",
                    }
                },
                "required": ["table"],
            },
        )

    def execute(self, table: str) -> str:
        """返回表的索引信息"""
        from data.mock_db import get_indexes

        indexes = get_indexes(table)
        if indexes is None:
            return f"表 '{table}' 不存在或没有索引信息"

        result = f"表 {table} 的索引:\n"
        result += f"{'索引名':<20} {'列名':<15} {'顺序':>5} {'非唯一':>8} {'基数':>10}\n"
        result += "-" * 60 + "\n"
        for idx in indexes:
            result += f"{idx['Key_name']:<20} {idx['Column_name']:<15} {idx['Seq_in_index']:>5} {'是' if idx['Non_unique'] else '否':>8} {idx['Cardinality']:>10}\n"

        return result


class ShowCreateTableTool(Tool):
    """查询建表语句"""

    def __init__(self):
        super().__init__(
            name="show_create_table",
            description="查看表的建表语句，包含字段定义、索引、引擎等信息",
            parameters={
                "type": "object",
                "properties": {
                    "table": {
                        "type": "string",
                        "description": "表名，如 orders、order_items",
                    }
                },
                "required": ["table"],
            },
        )

    def execute(self, table: str) -> str:
        """返回建表语句"""
        from data.mock_db import get_create_table

        result = get_create_table(table)
        if result is None:
            return f"表 '{table}' 不存在"
        return result
```

### 3. 创建数据库诊断场景配置

文件：`src/scenarios/db_diagnosis.py`

```python
"""数据库诊断场景的 System Prompt 和配置"""

SYSTEM_PROMPT = """你是数据库诊断专家，擅长分析 SQL 性能问题和优化数据库。

## 诊断流程
当你收到一个 SQL 性能问题，你应该按以下思路进行诊断：

1. **先获取执行计划**：调用 explain_sql 查看 SQL 的执行计划
2. **查看表结构**：调用 show_create_table 了解表结构和索引
3. **分析索引**：调用 show_index 检查现有的索引情况
4. **综合判断**：结合以上信息给出优化建议

## 工具使用规则
- 每次只调用一个工具，根据结果决定下一步
- 不要一次性调用多个工具
- 拿到所有需要的信息后，汇总分析给出最终答案

## 回答要求
- 用中文回答
- 诊断结论要具体，包括：问题根因、优化建议、预期效果
- 如果 SQL 性能良好，也说明为什么好

## 安全规则
- 只读分析，不执行任何写操作
- 不分析涉及密码、密钥的 SQL
"""

# 这是 LLM 看到的工具调用示例，帮助它理解应该怎么使用工具
TOOL_CALLING_EXAMPLE = """
用户问：分析这条SQL：SELECT * FROM orders WHERE status = 'PENDING'

你应该：
1. 调用 explain_sql(sql="SELECT * FROM orders WHERE status = 'PENDING'")
   → 发现 type=ALL，全表扫描
2. 调用 show_create_table(table="orders")
   → 看看 status 字段有没有索引
3. 调用 show_index(table="orders")
   → 确认现在有哪些索引
4. 综合判断，给出结论
"""
```

### 4. 更新 main.py

修改 `src/main.py`：

```python
"""CLI 入口"""

from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry
from src.core.agent import Agent
from src.tools.db_tools import ExplainTool, ShowIndexTool, ShowCreateTableTool
from src.scenarios.db_diagnosis import SYSTEM_PROMPT


def build_agent(api_key: str = "mock") -> Agent:
    """构造 Agent 实例"""
    llm = LLMClient(
        api_key=api_key,
        base_url="https://api.deepseek.com",
    )

    tools = ToolRegistry()
    tools.register(ExplainTool())
    tools.register(ShowIndexTool())
    tools.register(ShowCreateTableTool())

    return Agent(llm=llm, tools=tools, system_prompt=SYSTEM_PROMPT)


def main():
    agent = build_agent()

    print("=" * 50)
    print("数据库诊断 Agent 已启动")
    print("输入 SQL 语句进行分析，输入 'exit' 退出")
    print("测试用例：")
    print("  1. SELECT * FROM orders WHERE status = 'PENDING'")
    print("  2. SELECT * FROM orders ORDER BY create_time DESC")
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

### 5. 运行验证

```bash
cd D:/market-handsome/newproject/db-agent
python src/main.py
```

输入：

```
> SELECT * FROM orders WHERE status = 'PENDING'
```

观察输出，看 Agent 是否会：

1. 先调 `explain_sql` → 发现全表扫描
2. 再调 `show_create_table` → 看表结构
3. 再调 `show_index` → 看现有索引
4. 最后给出优化建议

---

## 验收标准

- [ ] Agent 能正确调用 `explain_sql` 工具
- [ ] Agent 能根据 EXPLAIN 结果决定下一步要调什么工具
- [ ] Agent 最终能给出诊断结论
- [ ] 输入 `exit` 能正常退出

### 预期输出示例

```
[Step 1/10]
  → 调用工具: explain_sql({"sql": "SELECT * FROM orders WHERE status = 'PENDING'"})
  ← 结果: EXPLAIN orders:
     查询类型: SIMPLE
     访问类型: ALL
     可能索引: None
     实际索引: None
     扫描行数: 50000
     额外信息: Using where
     ⚠️ 全表扫描，性能风险高

[Step 2/10]
  → 调用工具: show_create_table({"table": "orders"})
  ← 结果: CREATE TABLE `orders` ...

[Step 3/10]
  → 调用工具: show_index({"table": "orders"})
  ← 结果: 表 orders 的索引: ...

[Step 4/10]
最终诊断：...
```

---

## Git 提交

```bash
git add .
git commit -m "feat: 实现数据库诊断Tool系统（EXPLAIN/SHOW INDEX/SHOW CREATE TABLE）"
```

---

## 案例：如果 Mock 不够用怎么办

你随时可以往 `data/mock_db.py` 里加新的 SQL 模式：

```python
# 模式6：你的新 case
if "COUNT" in sql_upper and "GROUP BY" in sql_upper:
    return {
        "id": 1,
        "select_type": "SIMPLE",
        "table": "orders",
        "type": "ALL",
        "possible_keys": None,
        "key": None,
        "rows": 50000,
        "Extra": "Using temporary; Using filesort",  # 临时表 + 文件排序！
    }
```

---

## 下阶段预告

当前 Agent 只能诊断慢 SQL。下一阶段：增加记忆功能，让 Agent 能记住之前的对话上下文。
