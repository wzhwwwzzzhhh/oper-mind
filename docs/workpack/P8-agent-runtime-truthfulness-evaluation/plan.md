# P8-agent-runtime-truthfulness-evaluation · 工作包计划

> PRD：`docs/prd/agent-runtime/P8-agent-runtime-truthfulness-evaluation.md`（已确认，issue #98）
> Design：`docs/design/agent-runtime/P8Agent运行真实性与评测基线Design.md`
> Design Review：第四轮独立终审 PASS，无 P0–P3；用户已确认 9 项设计决策
> 分支：`codex/issue-98-agent-runtime-truthfulness`
> worktree：`D:/market-handsome/oper-mind/.tmp/worktrees/agent-runtime-truthfulness`
> 基线：`main` / `b91e67b`（PR #97）

## 范围

### 只做

- AC1–AC4：把 DB/Server/Log/Knowledge mock 行为改为由完整互斥工具 allowlist 与显式场景事实驱动；
  空/未知/混合菜单 fail closed，无领域或无场景事实时不调用工具并返回无证据。
- AC3–AC6：parallel 证据冲突才进入 Debate，Reflection 依据报告和证据前置条件产生
  `ok/skipped/failed/error`；无匹配不发虚假 Agent 启动事件，real 图顺序不变。
- AC7：Server 五个既有 Tool 仅在显式 mock 场景返回数值；real 依赖/采集失败返回结构化
  `unavailable`，状态一致穿过 Gateway、Trace、事件持久化和 TraceCard。
- AC8–AC9：建立 pytest 行为快照矩阵和分类校验器；重复运行稳定，跨角色调用、场景外证据、
  伪成功、未标注 mock、敏感泄漏等负向样例能按类别失败。
- AC10：请求主题、领域结论和最终报告走确定性公开安全投影；thinking、工具实参/输出、异常 message/
  traceback 不进入报告、Trace、日志、持久化资源或测试输出；TraceCard 只显示安全字段。
- AC11：数据库真实工具、知识检索、主机指标、ToolGateway 及前后端既有回归保持通过。
- AC12–AC13：仅在真实自动化与 mock 全链复验完成后回写完善清单 P0-3/P1-2、跑通验证 C3、路线图
  和 PRD/工作包证据；确认无 API、迁移、Connector 或真实外部访问。

### 明确不做

- 不新增 Agent、Tool、Connector、服务类型、真实外部数据源、网络/文件系统或高风险动作能力。
- 不改变 real 模式路由策略、direct/chain/parallel 顺序，不把 Knowledge 加入 chain，不接线 judge_llm。
- 不新增公开 API、OpenAPI 字段、页面、路由、CLI/Runner、数据库字段/迁移或配置项。
- 不从报告正文推断结构化事实，不补造 recommendations，不启用长期记忆、RAG、向量或 MCP。
- 不访问真实模型、数据库、日志目录、主机或用户服务；测试只用显式 mock、临时受管目录和替身。
- 不顺带清理 `data.mock_db` 文件、`_mock_response`、fallback/judge_llm 等 P0-6 其他死代码。

## 切片拆分

- [x] S1：显式 DB 场景事实 + 角色化 mock + 质量状态 + 报告/日志安全投影
  - 验收：AC1–AC6、AC10；四角色不跨工具，S2/S3 无 DB 事实即无证据，target=none 无启动事件，
    Debate/Reflection 状态诚实，query/SQL/路径/DSN/Key/traceback 哨兵不可见，real 图顺序不变。
- [x] S2：Server unavailable 端到端状态 + TraceCard 诚实消费
  - 验收：AC7、AC10、AC11；Server real 失败无固定数值，Gateway/Coordinator/Executor/持久化事件
    均为 unavailable，前端显示“不可用”并计入需关注，质量 skipped/failed 可见且不伪装全部通过。
- [x] S3：确定性评测矩阵、负向门禁与交付文档
  - 验收：AC8–AC9、AC11–AC13；四单域 + chain + parallel + 无匹配 + 拒绝/不可用全部机器判定，
    同场景双跑快照一致，坏快照按类别失败；全量门禁和 mock 全链复验通过后按实回写状态。

## 改动面（文件级）

### 后端生产代码

- 新增 `backend/src/core/mock_runtime.py`：角色工具 allowlist、场景事实判断、确定性 tool call/结论与
  mock 质量纯函数。
- 新增 `backend/src/core/public_projection.py`：请求主题、领域结论、最终报告安全投影。
- 修改 `data/scenarios.py`、`backend/src/tools/db_tools.py`：冻结 DB 场景事实；无事实即无证据，
  DB mock 分支停止使用场景外 fallback。
- 修改 `backend/src/core/llm.py`、`backend/src/core/agent.py`：角色化 mock 委托、安全错误码、内部步骤
  不记录工具实参/输出。
- 修改 `backend/src/core/graph.py`、`backend/src/core/coordinator.py`：mock 路由/质量状态、skipped 事件、
  无匹配不发启动事件、报告不接 thinking、日志不记录 traceback/message。
- 修改 `backend/src/agents/report_agent.py`：安全请求主题与领域结论，不原样回显 query。
- 修改 `backend/src/core/tool_registry.py`、`backend/src/core/tool_gateway.py`、
  `backend/src/tools/server_tools.py`：兼容字符串 Tool 的结构化结果与 unavailable 映射。
- 修改 `backend/src/infrastructure/diagnosis/coordinator_executor.py`、`backend/src/application/services.py`：
  最终报告二次投影；Knowledge/质量/unavailable 的安全事件白名单。

### 后端测试

- 新增 `backend/tests/support/__init__.py`、`backend/tests/support/agent_runtime_evaluation.py`、
  `backend/tests/test_agent_runtime_evaluation.py`。
- 修改 `backend/tests/test_llm_client.py`、`backend/tests/test_db_tools_real.py`、
  `backend/tests/test_db_lock_pool_tools.py`、`backend/tests/test_server_tools.py`、
  `backend/tests/test_tool_gateway.py`、`backend/tests/test_knowledge_agent.py`、
  `backend/tests/test_p2_diagnosis_adapter.py`、`backend/tests/test_p2b_tool_trace.py`。
- 按实现落点新增/扩展 ReportAgent、Coordinator caplog、应用持久化资源的安全哨兵测试；不使用真实资源。

### 前端

- 修改 `frontend/src/features/workbench/TraceCard.tsx`、
  `frontend/src/features/workbench/trace-card.test.tsx`：unavailable、质量节点、计数和安全摘要。
- 按需修改 `frontend/src/styles/workbench.css`：复用既有 warn/danger，补 skipped/unavailable 视觉等级。
- 不修改 `frontend/src/api/v1/generated.ts`，无 OpenAPI 生成。

### 文档

- 当前阶段：PRD 与域/总索引、Design、workpack 三件套和 `docs/workpack/README.md`。
- 交付阶段：`docs/完善清单.md`、`docs/跑通验证.md`、`docs/路线图.md`、PRD AC/DoD、证据与 Review。

### 明确无数据库与接口变更

- 无迁移、ORM 模型、公开 API/OpenAPI、Connector、配置、凭据或真实连接改动。

## 验证方法

后端（`backend/`）：

- S1 聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_agent_runtime_evaluation.py tests/test_llm_client.py tests/test_db_tools_real.py tests/test_db_lock_pool_tools.py tests/test_knowledge_agent.py -q`
- S2 聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_server_tools.py tests/test_tool_gateway.py tests/test_p2_diagnosis_adapter.py tests/test_p2b_tool_trace.py -q`
- 静态：`..\.venv\Scripts\python.exe -m ruff check src tests`、`..\.venv\Scripts\python.exe -m mypy src`
- 全量：`..\.venv\Scripts\python.exe -m pytest tests -q`

前端（`frontend/`）：

- 聚焦：`npm run test -- src/features/workbench/trace-card.test.tsx`
- 全量：`npm run typecheck`、`npm run test`、`npm run build`

全链与门禁：

- 用隔离临时应用库、mock 模式后端与 Vite 5174 跑一次浏览器/API 全链：四类 direct、一个 chain、
  一个 parallel、一个无匹配；核对 TraceCard/结果/事件无假调用、假通过或敏感哨兵。
- 不连接真实资源；Knowledge 使用 worktree 内临时受管目录并在验证后清理。
- `git diff --check`；检查改动没有 `.env`、`config.local.yaml`、凭据、API Key 格式、原始 SQL/异常/路径测试
  哨兵进入生产文案或提交内容。

## 提交计划

- `功能: 修正Agent模拟运行与质量状态`
- `测试: 建立Agent行为评测基线`
- 文档收口并入与对应实现最紧密的提交；整个工作包控制在 1–3 个提交，Test → Review 后集中提交。

## 状态

- [x] PRD 已确认并关联 issue #98
- [x] 专用分支/worktree 已创建，基线为 `main` / `b91e67b`
- [x] Design 第四轮独立终审 PASS（无 P0–P3）
- [x] 用户确认 Design 决策与本计划
- [ ] 实现、验证、独立代码 Review、提交与交付
