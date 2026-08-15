# P8-audit-export · 工作包计划

> 关联 PRD：`docs/prd/audit/P8-audit-export.md`（已确认，issue #79）
> 关联 Design：`docs/design/audit/P8审计导出Design.md`（已确认，2026-08-14 用户拍板 §6 决策 1–5）
> 分支：`feat/p8-audit-export`（基线 `main`，origin/main @ 5782221）
> worktree：`D:/market-handsome/oper-mind-worktrees/P8-audit-export`

## 范围

### 只做

- AC1（导出文件与列表同构）：新增 `GET /audit/export`——按过滤条件导出审计活动
  （Run + action 事件双源归并全量快照），内容与 `AuditActivityResource` 18 字段同投影，
  `Content-Disposition` 附件下载。
- AC2（过滤一致）：`from`/`to`、`service_id`、`action_type`（11 枚举）、`result`（10 枚举）
  过滤语义与 `GET /audit/activities` 一致（同一枚举与领域映射 + 测试断言等价）。
- AC3（空态）：无匹配记录 → `200` + 元信息块（条数 0）+ CSV 仅表头 / MD 仅元信息块，
  不抛错。
- AC4（超限明确）：单次导出 ≤ 5000 条（Design §6 决策 2）；超限 → 路由直抛
  `ApiV1Error(422, "EXPORT_LIMIT_EXCEEDED", ...)`，message 建议收窄时间窗，
  不返回截断未标明的半截文件。
- AC5（无敏感内容）：导出不含 CoT/Prompt/原始工具输出/原始 SQL/原始异常/凭据/DSN/`sk-`；
  文本字段 `session_title`/`summary` 复用 `tool_gateway.desensitize()` 兜底脱敏。
- AC6（审批人诚实）：仅 `approval_recorded` 项 `approval_actor` 为"未记录"，
  其余为空；不伪造身份。
- AC7（元信息）：导出文件含导出时间、过滤条件（未过滤项标注"无"）、条数、
  快照标注四要素；响应头 `X-Export-Count`。
- AC8（确定性）：相同条件重复导出内容一致（排序 `occurred_at desc, id desc`）。
- AC9（前端导出入口）：审计操作记录页页头新增"导出"按钮，携带当前已应用过滤条件
  （service_id/action_type/result/from/to）下载 CSV；导出中/成功（N 条）/空（0 条）/
  超限/失败诚实提示。
- AC10（回归）：`test_audit_api.py` 全绿；前端 `typecheck`/`test`/`build` 通过。
- 文档：`docs/接口清单.md` 审计行"导出/报表（另行排期）"→ 已交付标注（随收尾）。

### 明确不做

- 不做报表/图表/统计汇总（只做明细导出）。
- 不做定时导出 / 邮件发送 / 归档订阅。
- 不导出原始事件、Trace 内部事件、CoT/Prompt、原始工具输出、原始异常、凭据/DSN/`sk-`。
- 不新增持久化、无数据库迁移（复用 runs/action_events 既有表，只读快照）。
- 不改变 `GET /audit/activities` 契约与行为。
- 不做身份/权限模型；不把 `EXPORT_LIMIT_EXCEEDED` 加入 `APPLICATION_ERROR_STATUS` 映射表
  （Design D1 约定：路由直抛）。
- 不做分片导出 / 后台任务 / 异步生成。
- 前端首版入口仅 CSV 下载（Markdown 能力由 API 提供，不加入口）。
- 无配置项/环境变量；无 Connector/凭据/真实连接；`docs/prd/` 不动；
  `data/`、`demo/` 不动；不触碰其他 Agent 的工作包文件。

## 切片拆分（2 个独立可验收切片）

- [ ] S1：后端导出 API——`domain/audit_export.py` + `domain/audit_repositories.py`（端口扩展）+
  `infrastructure/persistence/audit_repositories.py`（全量方法）+ `application/audit_service.py`
  + `application/audit_export_renderer.py` + `application/errors.py` + `api/v1/routes.py`
  + `tests/test_audit_export_api.py`。
  验收语义：AC1（同构投影）、AC2（过滤一致，与列表同条件断言）、AC3（0 条空文件）、
  AC4（超限 422 与错误码、边界恰 5000/5001）、AC5（敏感字面量不进文件）、AC6（审批人"未记录"）、
  AC7（元信息四要素 + `X-Export-Count`）、AC8（两次导出一致）、AC10（`test_audit_api.py` 回归）。
- [ ] S2：前端导出入口——`client.ts`（下载函数）+ `AuditPage.tsx`（导出按钮与状态提示）+
  `AuditPage.test.tsx` + `test/handlers.ts`（export mock）+ `generated.ts`（generate:api）。
  验收语义：AC9（按钮携带当前过滤条件、成功下载、空/超限/失败诚实提示）+ AC10 前端回归。

## 改动面（文件级）

### 后端（新增）

- `backend/src/domain/audit_export.py` —— `AuditExportFormat`（csv/md）、`AuditExportResult`
  （items/truncated/exported_at）。
- `backend/src/application/audit_export_renderer.py` —— CSV/Markdown 渲染纯函数 +
  `desensitize` 兜底 + 元信息块生成。
- `backend/tests/test_audit_export_api.py` —— AC1–AC8 服务端面 + 边界/脱敏/确定性。

### 后端（修改）

- `backend/src/domain/audit_repositories.py` —— `AuditActivityRepository` 端口 Protocol 新增
  `list_all_activities(max_items, filters...)` 声明。
- `backend/src/infrastructure/persistence/audit_repositories.py` —— 实现
  `list_all_activities(max_items, ...) -> tuple[list[AuditActivityData], bool]`
  （两侧各取 max_items+1、归并、超限标志；复用既有 `_run_select`/`_action_select`/行收敛）。
- `backend/src/application/audit_service.py` —— `export_activities(max_items, filters...)`
  → `AuditExportResult`（超限抛 `AuditExportLimitExceededError`）。
- `backend/src/application/errors.py` —— `AuditExportLimitExceededError`
  （服务层边界信号，对应 422 `EXPORT_LIMIT_EXCEEDED`，路由捕获后直抛）。
- `backend/src/api/v1/routes.py` —— `GET /audit/export` 路由（`format` 枚举校验、窗口校验、
  超限直抛 `ApiV1Error(422, "EXPORT_LIMIT_EXCEEDED", ...)`、`StreamingResponse` +
  `X-Export-Count`/`X-Request-Id` 头）。

### 前端（新增 + 修改）

- `frontend/src/api/v1/client.ts` —— `export_audit_activities` 下载函数（blob/text + 头解析、
  非 2xx 解析 JSON error 抛 `ApiClientError`）。
- `frontend/src/features/audit/AuditPage.tsx` —— 页头"导出"按钮 + 导出中/成功/空/超限/失败提示。
- `frontend/src/features/audit/AuditPage.test.tsx` —— 导出交互测试（MSW）。
- `frontend/src/test/handlers.ts` —— `/api/v1/audit/export` handler（追加式）。
- `frontend/src/api/v1/generated.ts` —— `npm run generate:api` 重新生成（禁止手编）。

### 文档

- `docs/接口清单.md`（审计行导出标注，随收尾）、`docs/workpack/README.md`（活跃登记）。

### 明确无改动

- 无数据库迁移；无配置项/环境变量；无 Connector/凭据/真实连接；SSE 与 Run 执行链路、
  审批执行链、多 Agent 内核、`GET /audit/activities` 契约不动；`docs/prd/` 不动。

## 验证方法

- 后端（在 worktree `backend/` 下执行，使用主工作区共享 venv）：
  - 聚焦：`D:/market-handsome/oper-mind/.venv/Scripts/python.exe -m pytest tests/test_audit_export_api.py -q`
  - 回归：`D:/market-handsome/oper-mind/.venv/Scripts/python.exe -m pytest tests/test_audit_api.py tests/test_api.py -q`
  - 提交前跑全量 `D:/market-handsome/oper-mind/.venv/Scripts/python.exe -m pytest tests -q`
- 前端（在 worktree `frontend/` 下执行，node_modules 为共享 junction）：
  `npm run typecheck`、`npm run test`、`npm run build`。
- API 契约：`npm run generate:api` 重新生成 generated.ts（后端 8000 起服务，或
  OpenAPI 落盘免端口方式）。
- 门禁：`git diff --check`；只暂存本工作包文件，禁止 `git add .`；检查敏感字面量。

## 提交计划

- S1 后端导出 API：
  `feat: 审计导出——按条件导出审计活动 API（P8，issue #79）`
- S2 前端导出入口：
  `feat: 审计导出——审计页导出按钮与状态提示（P8，issue #79）`
- 每个切片完成后集中 Test → 独立子代理 Review → 提交；全部完成后经
  `dev-deliver`（fetch+merge main → push → PR → 合并 → 归档）。
