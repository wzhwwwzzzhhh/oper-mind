# P8-session-export · AC 证据表

> 状态：S1/S2 已实现，独立子代理审查 PASS（无 P0/P1）
> 关联：`docs/prd/session/P8-session-export.md`（issue #76）、`docs/workpack/P8-session-export/plan.md`

## AC 证据

| AC | 验收语义 | 证据（代码/接口/测试） | 状态 |
|---|---|---|---|
| AC1 | 导出包含会话标题与消息时间线 | `build_session_export_markdown`（`backend/src/application/session_export.py`）+ `test_导出包含会话标题与消息时间线` | ✅ PASS |
| AC2 | 导出包含各 Run 结论摘要 | `_run_summary_block`（query/status/severity/confidence/summary/证据摘要）+ `test_导出包含Run结论摘要` | ✅ PASS |
| AC3 | 会话不存在 → 404 | `SessionNotFoundError`（`SESSION_NOT_FOUND` → 404）+ `test_会话不存在返回404` | ✅ PASS |
| AC4 | 空会话明确空态 | `SessionExportDocument.empty=True` + 文档「无可导出内容」+ `test_空会话返回明确空态` + 前端 `test_空会话提示无可导出内容且不发起导出请求` | ✅ PASS |
| AC5 | 读取失败 → 503 | `SessionExportUnavailableError`（`EXPORT_UNAVAILABLE` → 503）；读取与构建均纳入映射，不落半截文档 + `test_读取失败返回503` | ✅ PASS |
| AC6 | 无 CoT/Prompt/原始工具输出/SQL/异常/凭据/`sk-`/完整 DSN | 既有公开投影字段子集 + `desensitize()` + 导出专用连接串兜底（窄 scheme 白名单）+ 失败 Run 错误白名单 + `test_导出不含敏感内容` | ✅ PASS |
| AC7 | 重复导出一致（确定性） | 文档仅稳定字段（无导出时间戳/随机标识符）+ `test_重复导出一致`（字节相等） | ✅ PASS |
| AC8 | 前端导出入口：下载/失败重试/空态提示 | `request_text` + `export_session_markdown`（client.ts）+ 会话页工具栏（WorkbenchPage.tsx）+ `session-export.test.tsx` 3 用例 | ✅ PASS |
| AC9 | 回归全绿 | 后端全量 `pytest tests -q` → **496 passed / 2 skipped**；前端 `typecheck` ✅、`build` ✅、`test` 见验证记录 | ✅ PASS |

## 验证记录

- 后端全量：`pytest tests -q` → **496 passed, 2 skipped**（2026-08-15，worktree venv，最终代码）
- 后端聚焦：`pytest tests/test_session_export.py -q` → **8 passed**
- 后端 lint：`ruff check` 全部改动文件 → **All checks passed**
- 前端：`npm run typecheck` ✅；`npm run build` ✅；`npx vitest run src/features/workbench/session-export.test.tsx` → **3 passed**
- 前端全量 `npm run test`：146 用例中 3 个既有 flaky 失败（App.test.tsx「停止调查/重新生成」按钮超时），
  已用 `git stash` 在干净基线（origin/main）复现同样 3 个失败——**与本工作包无关的机器性能抖动**，
  本工作包新增用例全绿
- 契约：OpenAPI 落盘 → `openapi-typescript` 重新生成 `generated.ts`（+55 行，含 export 端点；
  生成产物把 200 响应描述为 `application/json` 属生成器对无 `response_model` 端点的默认描述，
  实际返回 `text/markdown`，客户端 `request_text` 不依赖该 schema，**禁止手编**）
- 门禁：`git diff --check` 干净；`git status` 只含本工作包文件

## 已记录的取舍（独立审查 P2 项）

- **逐 Run 结果读取（N+1）**：`store.get_result(run.id)` 逐 Run 查询，最坏 200 次（`RUN_EXPORT_CAP`）。
  已确认 Design §2.1 明确采用逐 Run `get_by_run_id`（复用既有查询、无新 SQL 面），实现与 Design 一致；
  导出为低频操作，PRD 性能要求「与既有两列表查询数量级相当」在典型会话规模下成立；
  若后续出现大会话导出性能问题，可改批量 `WHERE run_id IN (...)`，不涉及契约变更。
- **构建步骤错误映射**：`render_markdown` 的读取与构建同在一个 try 内，`(SQLAlchemyError, ValueError)`
  统一映射 503（Design §2.4「聚合或构建任一步失败 → 503」）。

## 人工抽查（DoD）

- [ ] 导出文档人工抽查不含敏感内容（交付后抽查样例）
