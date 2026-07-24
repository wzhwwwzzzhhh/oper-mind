# OperMind — 多智能体运维诊断协作系统

基于多智能体协作的运维故障诊断系统，支持直达/链式/并行三种路由策略，集成 Debate 与 Reflection 质量保障机制。

## 技术栈

Python 3.10+、LangGraph、OpenAI SDK、FastAPI、React + TypeScript

## 目录结构

```
oper-mind/
├── src/
│   ├── api/               # HTTP API 契约与 SSE 事件
│   ├── core/              # 核心框架
│   │   ├── agent.py       # Agent 基类
│   │   ├── coordinator.py # Coordinator 路由调度
│   │   ├── llm.py         # LLM 调用封装
│   │   ├── tool_registry.py  # 工具注册中心
│   │   ├── debate.py      # 辩论引擎
│   │   ├── reflection.py  # 反思复审
│   │   └── approval.py    # 高危操作审批
│   ├── agents/            # 领域 Agent
│   │   ├── server_agent.py  # 服务器诊断
│   │   ├── db_agent.py      # 数据库诊断
│   │   ├── log_agent.py     # 日志分析
│   │   └── report_agent.py  # 报告生成
│   ├── tools/             # 工具实现
│   │   ├── db_tools.py    # DB 诊断工具集
│   │   ├── server_tools.py # 服务器工具集
│   │   └── log_tools.py   # 日志工具集
│   ├── memory/            # 记忆系统
│   ├── frontend/          # React + TS 前端
│   ├── app.py             # FastAPI 入口
│   └── main.py            # CLI 入口
├── data/                  # Mock 数据 + 测试用例
├── tests/                 # 测试
├── docs/                  # 文档
├── .venv/                 # 虚拟环境
└── requirements.txt
```

## 开发阶段

1. 环境搭建
2. 多 Agent 框架搭建（Coordinator + 注册机制）
3. DB Agent 完善（真实 MySQL 对接）
4. Server Agent（psutil 实时采集）
5. Log Agent（日志解析）
6. Debate + Reflection 机制
7. Report Agent + 结构化报告
8. 前端可视化（React + TS + ECharts）
9. 复合测试 + 实验对比
10. 论文撰写

## 常用命令

```bash
.venv\Scripts\activate          # 激活虚拟环境
python src/main.py              # 运行 CLI
uvicorn src.app:app --reload    # 启动 API
cd src/frontend && npm run dev  # 启动前端
```

## 开发规则

> 完整规范见 `docs/开发规范.md`（代码风格 / 架构约定 / Mock 纪律 / 安全 / Git / 测试 / 实验复现 / 文档，共 8 项）。
> 开发路线与排期见 `docs/开发路线图与规划.md`。
> 以下为必须遵守的核心硬约束：

- **注释用中文**；类名大驼峰，函数/变量小写下划线，常量全大写。
- **Tool** 继承 `Tool` 基类实现 `execute`；**Agent** 继承 `BaseAgent` 复用 ReAct 循环，不重写 `run()`。
- **公开函数必须带类型标注**；结构化数据用 Pydantic / TypedDict，不裸传 dict。
- **禁止裸 `except`**，禁止用 `print` 做生产日志。
- **Mock 模式（`api_key="mock"`）是一等公民**：每个外部依赖（LLM / MySQL / psutil）都必须有确定性 mock fallback，保证答辩演示可复现。
- **安全红线**：密钥只从环境变量读取，绝不进代码库；真实 DB 用只读账号 + 参数化查询，诊断工具禁止 DDL/DML；高危操作过审批门。
- **测试**：direct / chain / parallel 三条路径各有 mock 冒烟测试；改了 graph/debate/reflection/approval 必跑回归（`scripts/smoke_pipeline.py`）。
- **实验复现**：主实验跑 mock 模式，固定种子，结果落盘到带 config hash 的目录；评测装配必须关闭长期记忆的读取与写入，确保用例互不污染。
- **Git**：commit 用 `<类型>: <中文描述>`；不直推 `main`；不提交 `.env`/`*.local.yaml`/含 `sk-` 的文件。
- **改架构必须同步更新** `AGENTS.md` 与 `docs/开发规范.md`。
- **重要修改走文档驱动流程**：涉及架构/接口契约、安全、里程碑/论文实验产出或非平凡 bug 修复的改动，须在 `docs/初始开发/` 建一份分层开发日志（Design → Step → Code → Test → Review 五层），日志定位为「带日期+commit 的快照」，贴关键片段+`文件路径:行号`锚点而非整文件。详见 `docs/开发规范.md` 第 9 节。
