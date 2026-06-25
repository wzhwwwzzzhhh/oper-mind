# 数据库智能诊断 Agent

基于 ReAct 模式的数据库诊断 Agent，覆盖慢 SQL 分析和索引优化。

## 技术栈

Python 3.10+、OpenAI SDK、FastAPI、LangGraph

## 目录结构

```
db-agent/
├── src/
│   ├── core/              # 核心引擎
│   │   ├── llm.py         # LLM 调用封装（支持 mock 和真实 API）
│   │   ├── agent.py       # ReAct 循环引擎
│   │   ├── tool_registry.py  # Tool 注册中心
│   │   ├── fallback.py    # 规则引擎降级
│   │   └── approval.py    # 高危操作审批
│   ├── tools/
│   │   └── db_tools.py    # EXPLAIN/SHOW INDEX/SHOW CREATE TABLE
│   ├── memory/
│   │   ├── short_term.py  # Sliding Window 短期记忆
│   │   └── long_term.py   # JSON 持久化长期记忆
│   ├── scenarios/
│   │   └── db_diagnosis.py  # 诊断场景 System Prompt
│   ├── main.py            # CLI 入口
│   ├── agent_langgraph.py # LangGraph 版
│   └── app.py             # FastAPI 入口
├── data/
│   ├── mock_db.py         # Mock 数据（模拟 MySQL EXPLAIN）
│   └── test_cases.json    # 7 个测试用例
├── tests/
│   └── test_diagnosis.py  # 测试脚本
├── docs/                  # 开发文档
├── .venv/                 # 虚拟环境
└── requirements.txt
```

## 开发阶段

1. 环境搭建
2. Python 速成
3. 手搓 ReAct 引擎（llm.py → tool_registry.py → agent.py → main.py）
4. Tool 系统 + 数据库诊断
5. 记忆机制（短期 + 长期）
6. 降级策略 + 安全审批
7. LangGraph 重构
8. FastAPI 包装 + 测试
9. 面试准备

## 常用命令

```bash
.venv\Scripts\activate        # 激活虚拟环境
python src/main.py            # 运行 CLI
python src/main.py --fallback # 降级模式测试
uvicorn src.app:app --reload  # 启动 API
python tests/test_diagnosis.py # 运行测试
```

## 编码约定

- 注释用中文
- 类名大驼峰，函数/变量小写下划线
- Tool 继承 Tool 基类，实现 execute 方法
- Mock 模式：api_key="mock"，用于开发和测试
