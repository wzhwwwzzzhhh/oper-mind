# OperMind 开发规则

## 先读这些

- 当前产品与工程事实只来自 `docs/产品定义.md`、`docs/路线图.md`、`docs/开发规范.md`；任务记录、原型、报告和历史文档不能替代它们。
- 这是一个前后端仓库：后端在 `backend/`，前端在 `frontend/`，专用演示靶场在 `demo/`；不要把演示代码当成正式产品入口。
- 正式后端 API 主线是 `backend/src/app.py` 的 `src.app:app` 与 `/api/v1`；前端入口是 `frontend/src/app/App.tsx`。

## 常用命令

- 后端命令从 `backend/` 执行，使用仓库根 `.venv` 的 Python：`..\.venv\Scripts\python.exe -m pytest tests -q`。
- 后端单测：`..\.venv\Scripts\python.exe -m pytest tests/test_api.py -q`；将路径替换为目标测试文件即可运行聚焦测试。
- 后端开发服务：`..\.venv\Scripts\python.exe -m uvicorn src.app:app --reload --port 8000`。
- 数据库迁移必须显式执行，后端启动不会自动迁移：`..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head`。
- 前端命令从 `frontend/` 执行：先运行 `npm install`，再按需运行 `npm run dev`、`npm run typecheck`、`npm run test`、`npm run build`。
- 前端开发服务固定使用 Vite `5174` 端口；`/api` 默认代理到 `http://127.0.0.1:8000`，可用 `VITE_API_PROXY_TARGET` 覆盖。
- API 类型生成需要后端在 `8000` 提供 OpenAPI：`npm run generate:api`；生成的 `frontend/src/api/v1/generated.ts` 禁止手工编辑。
- 提交前至少运行相关测试、前端 `typecheck`/`test`/`build`（若涉及前端），以及 `git diff --check`；只检查和暂存本次改动文件，禁止无检查的 `git add .`。

## 代码边界

- 后端主要按 `api`、`application`、`domain`、`core`、`agents`、`infrastructure` 分层；跨层数据使用 Pydantic 或 TypedDict，禁止隐式字典协议。
- LLM Agent 继承 `BaseAgent` 并复用既有运行接口；Tool 继承 `Tool` 并实现受控 `execute`；确定性 Connector/Collector 通过显式 Application port 或 Executor 注入并返回结构化事实。
- 前端 API 访问集中在 `frontend/src/api/v1/`；交互页面位于 `frontend/src/features/`；测试使用 Vitest、jsdom 和 MSW，公共初始化在 `frontend/src/test/setup.ts`。
- 中文注释、文档和用户可见日志；公开函数必须有类型标注；禁止裸 `except` 和新增生产 `print`。
- 新增关键路径同时补后端单元/API 测试和前端交互测试；真实外部依赖使用确定性 mock，不得把 mock 描述成真实执行或实时监控。

## 配置与数据

- `config/config.local.yaml` 被 Git 忽略；配置优先级是环境变量覆盖 YAML。优先使用环境变量注入 `OPERMIND_API_KEY`、`OPERMIND_BASE_URL`、`OPERMIND_MODEL`、`OPERMIND_APP_DATABASE_URL` 等敏感或环境相关值。
- 应用元数据默认写入根目录 `data/opermind.sqlite3`，不与诊断目标服务复用连接；迁移使用同一应用数据库 URL。
- 不得提交 `.env`、`config.local.yaml`、凭据、API Key 或包含 `sk-` 的内容；凭据不得进入日志、数据库普通字段、Trace、事件、结果、截图或接口响应。
- 未经用户明确授权，不连接、探测、读取、写入或清理真实外部资源；真实资源测试必须先确认授权、目标边界和脱敏方式。

## 产品与安全约束

- 会话工作台是产品主入口，服务中心负责服务接入、服务状态、监控和调查入口；PostgreSQL 慢查询只是现有技术切片，不是产品边界。
- 前端不得直连 PostgreSQL、MySQL、Redis、日志系统或任何用户服务；所有外部访问只能经后端显式注册的 Connector/Tool，并具备参数校验、权限边界、超时、脱敏和审计摘要。
- 默认调查只读；模型不得直接拥有任意 SQL、Shell、DDL、DML 或网络访问能力。
- 高风险动作必须经过服务器提案、人工审批、严格白名单执行和独立 Verify；禁止自动批准、通用执行器和聊天文本直接执行。
- Trace UI 只展示角色、阶段、状态、耗时、工具类别和脱敏证据摘要；禁止展示 CoT、Prompt、原始工具输出、原始异常、原始 SQL 或凭据。
- 新增服务类型、Connector、真实连接、监控、凭据、权限、公开 API、数据库迁移、审批/执行能力或破坏性改动，必须先 Design → Review → 用户确认；未启用能力必须如实标明。

## Git 工作流

- 不直推 `main`；提交信息使用 `<类型>: <中文描述>`。
- 一个工作包只包含 1–3 个紧密切片，完成后集中 Test → Review → Commit；不要擅自提交，除非用户明确要求。
- 不回退或覆盖用户/其他 Agent 已有改动；发现冲突时先停下说明，不使用破坏性 `git reset --hard` 或 `git checkout --`。
