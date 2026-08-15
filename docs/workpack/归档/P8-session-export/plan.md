# P8-session-export · 工作包计划

> 关联 PRD：`docs/prd/session/P8-session-export.md`（已确认，issue #76）
> 关联 Design：`docs/design/session/P8会话导出Design.md`（草稿 → 本工作包确认后置「已确认」）
> 分支：`feat/P8-session-export`（基线 `origin/main`，8a644f3）
> worktree：`D:/market-handsome/oper-mind-worktrees/P8-session-export`

## 范围

### 只做

- AC1–AC2（导出文档，Design §2.1）：新增 `GET /sessions/{session_id}/export`，返回
  `text/markdown` 安全摘要文档：会话标题 + 创建时间 + 状态、消息时间线（user/assistant/system
  正文安全投影）、各 Run 结论摘要（问题/状态/目标服务/severity/confidence/summary/证据摘要/白名单错误）。
- AC3（404）：会话不存在 → `404 SESSION_NOT_FOUND`（复用 `SessionNotFoundError`）。
- AC4（空态）：无消息无 Run → 200 空态文档（导出头 + 「无可导出内容」），不抛错不伪造。
- AC5（503）：聚合读取失败 → `503 EXPORT_UNAVAILABLE`，不返回半截文档。
- AC6（无敏感内容）：导出字段全部为既有公开投影子集；所有文本字段过 `desensitize()` 兜底；
  失败 Run 错误经 `_safe_run_error` 白名单。
- AC7（确定性）：文档只含稳定字段（无导出时间戳/随机标识符），重复导出字节一致。
- AC8（前端导出入口，Design §2.2）：会话页工具栏「导出」按钮 → 下载 Markdown；
  导出中展示进行态；失败展示错误与重试；空会话提示「无可导出内容」（不发请求）。
- AC9（回归）：既有 `test_api.py` 与会话消息相关测试全绿；前端 `typecheck`/`test`/`build` 通过。
- 文档：`docs/接口清单.md` 缺表「会话导出」标记已交付 + 补 `GET /sessions/{id}/export` 行；
  `docs/路线图.md` 当前阶段登记本工作包（issue #76）。

### 明确不做

- 不导出原始证据包：工具原始输出、SQL、日志原文、Trace 内部事件、Prompt/CoT、异常堆栈、凭据。
- 不做批量导出 / 全局导出 / 定时导出 / 导出订阅 / 邮件发送；不做导出后编辑 / 回传。
- 不做 JSON 变体（v1 仅 Markdown，Design 待确认决策 1）；不做分页导出（按上限截断并注明，
  Design 待确认决策 3）。
- 不改变既有会话 / 消息 / Run 接口契约与留痕；不改 SSE 与 Run 执行链路。
- 无数据库迁移、无配置项、无 Connector/凭据、无权限/审批/执行能力变化；`docs/prd/` 不动。

## 切片拆分（2 个独立可验收切片）

- [ ] S1：导出接口（后端）——`session_export.py` 应用服务 + 纯函数文档构建 +
  `SessionExportUnavailableError` + `GET /sessions/{session_id}/export` 路由 + 后端测试。
  验收语义：AC1（标题与消息时间线）、AC2（Run 结论摘要）、AC3（404）、AC4（空态文档）、
  AC5（读取失败 503）、AC6（无敏感内容）、AC7（重复导出一致）。
- [ ] S2：导出入口（前端）——`client.ts` 下载方法 + WorkbenchPage 工具栏 + MSW mock + 交互测试。
  验收语义：AC8（下载/失败重试/空态提示）、AC9（前端回归）。

## 改动面（文件级）

### 后端（新增 + 修改）

- `backend/src/application/session_export.py`（**新增**）：`SessionExportApplicationService`
  （注入 `session_factory`，对齐 `audit_service.py` 只读服务先例）、
  `build_session_export_markdown` 纯函数、`SessionExportDocument`、上限常量
  （`MESSAGE_EXPORT_CAP=500`、`RUN_EXPORT_CAP=200`、`EVIDENCE_PER_RUN_CAP=50`）、
  导出专用连接串兜底脱敏（窄 scheme 白名单，覆盖无凭据完整 DSN）。
- `backend/src/application/errors.py`（修改）：新增 `SessionExportUnavailableError`
  （`code="EXPORT_UNAVAILABLE"`，`APPLICATION_ERROR_STATUS` 映射 503）。
- `backend/src/infrastructure/persistence/repositories.py`（修改）：新增
  `SqlAlchemyMessageRepository.list_latest_by_session` 与
  `SqlAlchemyDiagnosisRunRepository.list_latest_by_session`
  （有界尾部查询：倒序取最近 N 条再正序重排；既有 `list_by_session` 契约不变）。
- `backend/src/api/v1/routes.py`（修改）：新增 `GET /sessions/{session_id}/export` 路由
  （成功返回 `Response(content=markdown, media_type="text/markdown; charset=utf-8")` +
  `Content-Disposition`；`SessionNotFoundError` → 404；`SessionExportUnavailableError` → 503）。
- 后端测试（新增）：`tests/test_session_export.py`。

### 前端（修改）

- `frontend/src/api/v1/client.ts`（修改）：内部 `request_text`（与 `request_json` 同构，
  `Accept: text/markdown`，非 2xx 解析 JSON 错误体抛 `ApiClientError`）+
  `export_session_markdown(session_id, options?) -> Promise<{ text, filename }>`。
- `frontend/src/api/v1/generated.ts`（`npm run generate:api` 重新生成，禁止手编）。
- `frontend/src/features/workbench/WorkbenchPage.tsx`（修改）：会话区顶部工具栏「导出」按钮
  （`useMutation` 下载；进行态禁用；失败 `ApiErrorNotice` + 重试；空会话提示不发请求）。
- `frontend/src/test/handlers.ts`（修改）：`GET /sessions/:session_id/export` MSW mock。
- 前端测试（新增）：`frontend/src/features/workbench/session-export.test.tsx`。

### 文档

- `docs/接口清单.md`、`docs/路线图.md`、`docs/workpack/README.md`（活跃表登记）。

### 明确无改动

- 无数据库迁移（复用 sessions/messages/diagnosis_runs/diagnosis_results 既有表）；
  无配置项/环境变量；无 Connector/凭据；SSE 与 Run 执行链路不动；`data/`、`demo/` 不动。
- `docs/prd/` 内容不改（仅按流程做状态翻片登记：`P8-session-export.md` 与两级 README
  的「已确认 → 进行中」，属仓库登记约定，非需求变更）。

## 验证方法

- 后端（在 worktree `backend/` 下执行，使用 worktree 内重建的 venv）：
  - 聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_session_export.py -q`
  - 回归：`..\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_p2_api_v1.py -q`
    （提交前再跑全量 `tests -q`）
- 前端（在 worktree `frontend/` 下执行）：`npm run typecheck`、`npm run test`、`npm run build`。
- API 契约：后端起 8000 → `npm run generate:api` 重新生成 generated.ts（或 OpenAPI 落盘免端口方式）。
- 门禁：`git diff --check`；`git diff origin/main...HEAD --name-only` 只含本工作包文件；
  只暂存本工作包文件，禁止 `git add .`。

## 提交计划

- S1 后端导出接口：
  `feat: 会话导出——GET /sessions/{id}/export 安全摘要文档（P8，issue #76）`
- S2 前端导出入口：
  `feat: 会话页导出入口——一键下载安全摘要文档（P8，issue #76）`
- 每个切片完成后集中 Test → 独立子代理 Review → 提交；全部完成后经
  `dev-deliver`（fetch+merge main → push → PR → 合并 → 归档）。
