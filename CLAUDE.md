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

## 当前计划与里程碑

- **M5 之后的唯一进度真相源**：`docs/开发/_A-Plan-总览.md`。
- 当前执行顺序：M5 多 Agent 对比 → M6 后端 SSE → M7 前端可视化 → M8 端到端打磨与面试材料。
- 历史路线图 `docs/开发路线图与规划.md` 的 M5 之后定义仅供参考，不作为当前执行依据。

## 常用命令

```bash
.venv\Scripts\activate          # 激活虚拟环境
python src/main.py              # 运行 CLI
uvicorn src.app:app --reload    # 启动 API
cd src/frontend && npm run dev  # 启动前端
```

## 开发规则

> `AGENTS.md` 与 `CLAUDE.md` 是**同一份精简硬约束的镜像**；两者内容必须保持一致。
> 完整规范的唯一真相源是 `docs/开发规范.md`；开发进度的唯一真相源是 `docs/开发/_A-Plan-总览.md`。

- **代码规范**：注释用中文；类名大驼峰，函数/变量小写下划线，常量全大写；公开函数必须带类型标注；跨层结构化数据用 Pydantic / TypedDict，不裸传 dict；禁止裸 `except` 和新增生产 `print`。
- **架构套路**：Tool 继承 `Tool` 并实现 `execute`；Agent 继承 `BaseAgent` 并复用 ReAct `run()`；HTTP API 契约和 SSE 事件放 `src/api/`；Graph 状态走显式 `DiagnosisState`。
- **Mock 与安全**：`api_key="mock"` 是一等公民；每个外部依赖必须有确定性 mock fallback。密钥只读环境变量，真实 DB 仅只读账号和参数化查询，诊断工具禁 DDL/DML，高危操作必须经过审批门。
- **测试与复现**：测试默认 mock；direct / chain / parallel 均需冒烟覆盖。修改 graph / debate / reflection / approval 必跑 `scripts/smoke_pipeline.py`。评测必须关闭长期记忆读写，实验固定种子并以 config hash 落盘。
- **重要改动工作流**：架构、接口契约、安全、里程碑产出和非平凡 bug 均按 **Design → Step → Code → Test → Review → Commit** 执行。每个 step 收尾即做 Review；架构/删文件/非平凡改动须独立 code review 通过后才能提交；测试、审查、Git 不可后置。
- **开发日志**：A-Plan 期间的重要开发日志默认放 `docs/开发/M<N>-<名称>/`：`design.md`、一个或多个 `stepN-*.md`、`review.md`。跨里程碑的规则/流程治理日志放 `docs/开发/治理-<名称>/`。日志是带日期与 commit 的快照，记录关键片段和 `文件路径:行号` 锚点，不贴整文件。`docs/初始开发/` 是历史归档，不再新增日志。
- **文档同步**：目录、节点流、Agent/Tool 关系、API/SSE 契约或工作流变更时，必须同步更新 `AGENTS.md`、`CLAUDE.md`、`docs/开发规范.md`；影响里程碑状态时同时更新 `docs/开发/_A-Plan-总览.md`。
- **Git**：每个里程碑开独立 `feat/mN-*` 分支；commit 使用 `<类型>: <中文描述>`；不直推 `main`；不提交 `.env`、`*.local.yaml`、凭证或含 `sk-` 的文件。