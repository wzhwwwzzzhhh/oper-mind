# V2-1-main-agent-foundation · 工作包计划

> 状态：实现、自测与独立审查完成（PASS，P0/P1=0）；已建 PR [#139](https://github.com/wzhwwwzzzhhh/oper-mind/pull/139)，CI 全绿，待用户验收/合并
> 关联：PRD `docs/prd/agent-runtime/V2-1-main-agent-foundation.md`（Issue #137，已确认）；Design `docs/design/agent-runtime/V2-1单主Agent地基Design.md`（已确认）。
> 分支：`feat/v2-1-main-agent-foundation`；worktree：`D:/market-handsome/oper-mind-worktrees/v2-1-main-agent-foundation`；基线：本地 `main` 548baa9（`git fetch origin main` 因网络失败，本地 main 已含最新提交）。

## 范围

### 只做

- AC1／AC6：Capability 契约 v1 + 显式注册表（id+version、未知／重复／未激活／类型不符安全失败、最高版本激活、内部 catalog、无能力 id 分支）。
- AC2／AC4：`ops.readonly_playbook@1` 知识型能力；内置受管 Skill 的版本／大小／摘要校验；装入、降级、不可用观察、重复降级硬失败；知识辅助回答。
- AC5：`text.literal_compare@1` 迁移到通用契约，行为与 V2-0 一致；比较交付仍由确定性工具产生并完整复算。
- AC7／AC8／AC9／AC13：ReAct 有界循环；决策数／知识加载数／工具调用数／严格 120 秒预算（单次模型超时 = min(30s, 剩余)、工具等待 = min(3s, 剩余)）；取消粒度 = step 边界、调用返回后丢弃结果、无迟到写入；未知决策／额外字段／非法材料引用零工具执行。
- AC3／AC11／AC12：公开交付区分普通回答／知识辅助回答／追问／比较；知识标注固定前缀与禁词约束；Run 资源加法字段 `knowledge_grounding`、`main_capabilities`（used/degraded/steps，不含 catalog）、`main_capabilities_status`、`main_knowledge`；前端能力条覆盖成功／失败／取消／交付不可用终态。
- AC10／AC17／AC18：模型观察、事件、列表、详情、导出、日志不出现材料原文／原始工具输出／原始异常／凭据；mock 如实标注；无数据库迁移。
- AC14／AC15／AC16／AC19／AC20：重跑／幂等／规则版本／损坏行投影保持；V1 默认入口与 V1 调查链零改动；公开字段加法；后端全量、前端三件套、ruff／mypy／git diff --check、敏感字面量扫描通过；不引入子 Agent、真实连接、新依赖或 V1 退役。

### 明确不做

- 不新增公开端点、数据库表、迁移、事件类型、依赖、Connector、凭据、权限模型、审批或真实外部连接。
- 不新增交付 kind，不改 `run_deliveries.kind` CHECK。
- 不改 V1 Coordinator／领域 Agent／`LegacyDiagnosisRunAdapter`／V1 默认入口／历史 fixture。
- 不引入子 Agent、多主 Agent、长期记忆、Recovery、RAG／MCP／Embedding／热加载。
- 不做服务绑定／资源输入（留给 V2-2）；V2-1 输入契约只支持 material slots。
- 不把知识型能力做成检索或实时读取；知识辅助回答不得标为“已校验／已读取／已诊断”。
- 不修改 `core/react_graph.py`、`core/tool_gateway.py`、`core/tool_registry.py`、`core/llm.py`。
- 不手工编辑 `frontend/src/api/v1/generated.ts`。

## 切片拆分

- [x] S1 契约与注册表：`contract.py`、`registry.py`、`text_compare.py` 迁移、决策联合泛化；旧 `get()`／`definitions()` 兼容层；版本激活策略与测试。
- [x] S2 知识源与知识能力：`skill_source.py`、受管手册、`playbook` 声明、Skill 降级与知识辅助交付。
- [x] S3 ReAct 内核与预算：`main_agent_react.py`、`main_agent_budget.py`、`capability_tools.py`、`observation.py`、执行器逐步 yield、取消、删除旧 DAG。
- [x] S4 公开投影与事件：schemas／resources／routes、`RunApplicationService` 能力白名单与交付复核注入、批量事件汇总、`generated.ts` 重生成。
- [x] S5 前端与端到端证据：readers／MainDeliveryPanel／MainCapabilityStrip／WorkbenchPage／TraceCard／Composer、前端用例、两条路径复验。

> 切片按依赖顺序实施；每片完成即跑聚焦测试，S5 后跑全量三件套。用户已确认的 Design 明确要求 S1–S5，故保持五片（每片可独立验收）。

## 改动面（文件级）

后端新增：

- `backend/src/capabilities/contract.py`
- `backend/src/capabilities/registry.py`
- `backend/src/capabilities/skill_source.py`
- `backend/src/capabilities/playbook/__init__.py`
- `backend/src/capabilities/playbook/readonly_playbook.md`
- `backend/src/core/main_agent_decisions.py`
- `backend/src/core/main_agent_react.py`
- `backend/src/core/main_agent_budget.py`
- `backend/src/core/capability_tools.py`
- `backend/src/core/observation.py`
- `backend/tests/test_capability_contract.py`（契约、注册表、知识源、预算与决策校验）
- `backend/tests/test_main_agent_runtime.py`（ReAct 多步、知识降级、四类取消、版本激活 rerun、严格预算）
- `backend/tests/test_main_agent_runs_api.py`（公开投影、事件白名单、批量查询、OpenAPI 契约）

后端修改：

- `backend/src/capabilities/__init__.py`（迁出注册表，保留兼容再导出）
- `backend/src/capabilities/text_compare.py`
- `backend/src/core/main_agent_model.py`
- `backend/src/core/main_agent_graph.py`（删除）
- `backend/src/agents/main_agent.py`
- `backend/src/domain/main_agent.py`
- `backend/src/application/run_execution.py`
- `backend/src/application/services.py`
- `backend/src/infrastructure/agent_runtime/run_executor.py`
- `backend/src/infrastructure/persistence/repositories.py`（新增批量事件读取，无 schema 变更）
- `backend/src/api/v1/{dependencies,routes,schemas,resources}.py`
- 相关既有测试：`tests/test_main_agent_runtime.py`、`tests/test_main_agent_runs_api.py`、`tests/test_runs_list.py`（加法字段）；`tests/test_text_compare.py` 行为断言未改。

前端修改：

- `frontend/src/features/workbench/main-delivery-readers.ts`
- `frontend/src/features/workbench/MainDeliveryPanel.tsx`
- `frontend/src/features/workbench/MainCapabilityStrip.tsx`（新增）
- `frontend/src/features/workbench/WorkbenchPage.tsx`
- `frontend/src/features/workbench/TraceCard.tsx`
- `frontend/src/features/workbench/MainAgentComposer.tsx`
- `frontend/src/api/v1/generated.ts`（仅 `npm run generate:api`）
- 相关测试：`main-delivery-readers.test.ts`、`main-delivery.test.tsx`、`main-capability-strip.test.tsx`（新增）、`main-agent.test.tsx`、`trace-card.test.tsx`

**数据库变更**：无。**公开端点变更**：无（仅响应加法）。**事件类型**：无新增。**依赖**：无新增。

## 验证方法

后端（在 worktree/backend，使用仓库根 `.venv`）：

```bash
D:/market-handsome/oper-mind/.venv/Scripts/python.exe -m pytest tests -q
D:/market-handsome/oper-mind/.venv/Scripts/python.exe -m pytest tests/test_capability_contract.py tests/test_main_agent_runtime.py tests/test_main_agent_runs_api.py -q
D:/market-handsome/oper-mind/.venv/Scripts/python.exe -m ruff check src tests
D:/market-handsome/oper-mind/.venv/Scripts/python.exe -m mypy src
```

前端（在 worktree/frontend）：

```bash
npm install
npm run typecheck
npm run test
npm run build
npm run generate:api   # 需 8000 端口后端；或用 app.openapi() 落盘后 npx openapi-typescript
```

其他：

```bash
git diff --check
# 敏感字面量扫描：sk-、password=、真实 DSN 等（排除测试中的显式假值）
```

专项证据（AC 映射）：契约／注册表、知识装入与降级、ReAct 多步、四类取消、版本激活 rerun、严格预算、公开资源与事件白名单、前端知识徽标与禁词、失败／取消终态能力条、V1 回归。

## 提交计划

- `feat: 建立 V2-1 能力契约与注册表`
- `feat: 接入只读排查手册知识能力`
- `feat: 实现主 Agent ReAct 内核与严格预算`
- `feat: 投影 V2-1 能力与知识公开字段`
- `feat: 展示主 Agent 能力、步骤与知识标注`
- `docs: 补 V2-1 Workpack 计划、审查与证据`

> 提交信息按实际改动调整；不直推 main，最终一个 PR（代码 + Design + Workpack）。

## 已知边界（必须写入 evidence）

- 回滚时旧代码会把带 `knowledge_grounding` 的交付行判为 `unavailable`（安全不可用投影，不 500、不伪造）；比较与追问行不受影响。
- `git fetch origin main` 因网络失败，worktree 基于本地 main 548baa9；合入前需重新 fetch／merge 并解冲突。
- 模型单次调用实际超时通过每 Run 客户端工厂按 `min(30s, 剩余预算)` 创建；`core/llm.py` 不改。
- 工具等待按每次调用创建临时网关实现 `min(3s, 剩余预算)`；网关本身不改。
