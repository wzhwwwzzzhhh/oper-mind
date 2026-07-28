# P3.4 Step 设计 — 结构化结果、终态收口与受控 Trace 边界

> 日期：2026-07-28　|　状态：✅ P3.4b 已完成代码、验证与独立 Review；等待 P3.4c 代码授权
>
> 工作分支：`feat/p3-workbench`　|　设计基线：`306724d docs: 校正P3.3c提交状态并进入P3.4`

## 1. 目标与固定边界

本 Step 将 P2 的 `DiagnosisRun.result` 设计为 P3 工作台唯一的结构化结果来源，并收口 success / failed / cancelled / queued / running、合法空数组、归档只读和协议读取异常。P3.4 不新增后端接口、不修改 OpenAPI/ORM/Alembic、不消费旧 `/diagnose*`，不连接真实数据库或数据源，也不改造 `report/`。

`DiagnosisResult` 是随 `GET /api/v1/runs/{run_id}` 返回的嵌入资源。它不是 Message、RunEvent 或 Markdown 的推导结果；`report_markdown` 只是补充字段，P3.4 不渲染或导出。

## 2. P3.4a — 结构化结果读取模型与摘要面板

### 交付

1. 新增窄化的 Result 运行时 reader，校验选定 Run、`result.run_id`、必填字段、枚举、数值范围和 UTC `Z` 时间；Reader 不接受未知 Run/不完整 Result 并返回安全协议问题。
2. 新增只读 `DiagnosisResultPanel`：摘要、severity/confidence、根因、证据与页内关联；数组为空展示局部空状态。
3. 新增 Result reader/面板的单元与组件测试，夹具覆盖完整合法 Result、空数组、错配 run_id、缺 `created_at`、错误时间和未知枚举。

### 实际交付与验证

- 新增 `frontend/src/features/workbench/result-readers.ts:1-340`：对 P2 `DiagnosisResult` 的顶层和嵌套字段做运行时窄化，校验选定 `run_id`、全部必填字段、合法枚举、置信度、UTC `Z`、原子 attributes 与 agent duration；协议问题返回安全 `issues`，不构造成功结果。
- 新增 `frontend/src/features/workbench/DiagnosisResultPanel.tsx:1-105`：只读渲染 severity/confidence/时间、摘要、根因、证据、页内 evidence 关联和局部空状态；不解析 `report_markdown`、不生成链接、不访问 locator/Trace。
- 新增 `frontend/src/features/workbench/diagnosis-result.test.tsx:1-115`：覆盖完整 Result、run_id 错配、缺 `created_at`、未知 severity、越界 confidence、非 UTC 时间、合法空字符串、缺失证据页内标记、空数组、Markdown/外链不渲染。
- 已通过：`npm run typecheck`；`npm run test`（4 files / 32 passed）；`npm run build`。构建仍有既有单 chunk 大于 500 kB 的非阻断 Vite 提示，本 Step 不做拆包。

### 不做

- 不改 `WorkbenchPage` 的 failed/cancelled/归档收口，不新增外部 Trace 链接；
- 不修改 MSW 或独立 FastAPI Mock，不接触 8000、数据库、`report/`；
- 不显示建议执行、审批、环境、告警、Incident、知识或报告 UI。

### 实现文件上限与建议验证

预计不超过 4 个前端源码/测试文件：`result-readers.ts`、`DiagnosisResultPanel.tsx`、其测试与必要样式；若需要跨越该范围，先更新 HANDOFF。最低验证为 Result 单元/组件测试、`npm run typecheck`、`npm run test`、`npm run build`。

## 3. P3.4b — 选定 Run 的终态、空状态与归档收口

### 交付

1. 将 P3.4a 面板接入 `SelectedRun`，只在成功 Run 且 Reader 合法时显示；`failed` 只显示安全 `Run.error`，`cancelled` 显示中性取消终态，非终态显示进度而非结果。
2. 把 Result、Event、Run 读取失败分离：API/网络/非 JSON/协议错误仍走安全 API 错误提示，不能写成业务失败。
3. 完善 active 无 Run、Result 局部空数组、无 Event 的成功 Result、归档 Session 历史只读、404/跨 Session 与切换 Run 的回归测试。

### 实际交付与验证

- 修改 `frontend/src/features/workbench/WorkbenchPage.tsx`：新增 `RunOutcomePanel`，将 P3.4a `DiagnosisResultPanel` 接入 `SelectedRun`。成功 Run 仅在 `result.run_id` 与完整 Result reader 合法时展示；不完整 Result、状态载荷矛盾和未知状态均显示 `RESULT_PROTOCOL_ERROR`，不复用旧结果或构造结论。
- `failed` 只显示服务端返回的安全 `error.code` / `error.message`；`cancelled` 明确不推断原因；`queued` / `running` 显示真实进度提示且不展示 Result。读取 API/网络/非 JSON 错误仍由既有 `ApiErrorNotice` 区分处理。
- 归档 Session 的 Run 仍为只读：可显示合法历史成功 Result，既有提交区继续移除问题输入与“开始诊断”按钮。
- 修改 `frontend/src/app/App.test.tsx`：既有深链的简化 Result 改为断言 `RESULT_PROTOCOL_ERROR`；新增成功、协议异常、failed、cancelled、queued、running 和归档历史 Result 的路由回归。
- 已通过：`npm run typecheck`；`npm run test`（4 files / 37 passed）；`npm run build`。构建主 chunk 因 P3.4a 面板正式接入增至约 893 kB，仍为既有大 chunk 非阻断提示；本 Step 不混入拆包。

### 不做

- 不实现重新执行、取消、恢复、归档编辑、审批、操作建议执行或报告导出；
- 不从事件、消息或 `report_markdown` 造结构化字段；
- 不开始 P4/P5/P6 资源、页面、假数据或真正 Trace 跳转。

## 4. P3.4c — 完整 Result 的 Mock 契约与独立验收

### 交付

1. MSW 与 `frontend/scripts/mock_v1_api.py` 提供完整 P2 `DiagnosisResult`：包含 `created_at`、非空与空数组、impact、建议、风险、Agent 摘要和失败/取消/非终态场景；不引入未定义字段。
2. 扩展 mock 自动测试，确认 Result 终态不变量、错误资源、UTC `Z`、request/trace 关联和安全错误。
3. 使用独立 8100 Mock 与明确指向它的 5175 Vite 验收：成功结果、失败、取消、归档历史、刷新深链、Result 读取错误与无 Trace 入口。临时实例必须关闭。

### 不做

- 不连接用户运行中的 8000/5174、真实数据库、真实 Agent 或真实数据源；
- 不把进程内 Mock 说成 P2 persistence/队列验收；
- 不修改后端、旧接口、`report/` 或运行时数据文件。

## 5. 受控 Trace 入口的停止条件

P3.4 不生成任何 Trace URL、按钮或 iframe。未来 P6 想开放入口前，必须具备并评审显式外部地址配置、trace deep-link 契约、认证授权、窗口/状态隔离、不可用回退和审计边界；任意条件缺失则继续无入口。`trace_id` 只可作为安全关联文本显示。

## 6. 审查清单与唯一下一步

Review 必须逐项核对：P2 `DiagnosisResult`/终态不变量；成功/失败/取消与 API 错误区分；空数组和归档只读；刷新/SSE 不把事件当 Result；Mock 完整性；`report/`、P4/P5/P6、真实资源和旧 API 均未混入；文档、计划和 AGENTS/CLAUDE 的唯一下一步一致。

**P3.4b 已完成并通过独立 Review。当前唯一下一步为 P3.4c：补齐完整结构化 Result 的 MSW/独立 Mock FastAPI 契约，并完成独立代理与人工验收；需用户明确代码授权后才可开始。**
