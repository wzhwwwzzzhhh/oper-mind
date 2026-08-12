# P8-audit-activity-log · 工作包计划

> 关联 PRD：`docs/prd/audit/P8-audit-activity-log.md`（已确认，issue #62）
> 关联 Design：`docs/design/audit/P8审计操作记录Design.md`（草稿 → 本工作包确认后置「已确认」）
> 分支：`feat/p8-audit-activity-log`（基线 `main`）
> worktree：`D:/market-handsome/oper-mind-worktrees/p8-audit-activity-log`

## 范围

### 只做

- AC1（跨服务跨会话分页列表，Design D1）：新增 `GET /audit/activities`——统一审计流双源
  （`diagnosis_runs` + `action_events`）有界归并（每侧 limit+1、Python 归并、(time desc, id desc)
  键集游标 `AuditActivityCursor(created_at, id)`），返回 `AuditActivityResource` 安全摘要分页。
- AC2（时间窗过滤）：`from`/`to` 可选参数，A 侧作用于 run.created_at、B 侧作用于
  event.occurred_at；`from > to` → 422 明确错误。
- AC3（service_id 过滤）：按 `DiagnosisRunRecord.service_id`（Run 权威归属，覆盖 P6 多服务会话）
  过滤；未知 service_id → 200 空列表，不抛错、不做 registry 校验。
- AC4（类型过滤）：`action_type` 11 值枚举（5 Run 派生 + 6 里程碑 action 事件，Design D2），
  非法值 → 422。
- AC5（结果过滤）：`result` 10 值枚举（含 expired，action_failed 按 data.status 派生；
  approval_recorded 按 data.status 派生 approved/rejected），非法值 → 422。
- AC6（脱敏纪律）：Run 项复用 `service_activity` 收敛字段（summary ≤800/severity/confidence/
  proposal_status/verification_status）；Action 项仅提取事件 data 白名单字段
  （summary ≤500/mode/status/action_id，资源层二次限长兜底），绝不整包 dump data；
  不暴露凭据/DSN/`sk-`/原始工具输出/异常详情。
- AC7（审批人诚实）：仅 `approval_recorded` 项 `approval_actor` 恒为 `"未记录"`；
  审批决策与时间如实展示；action 项 `action_id`/`mode` 可空（该事件 data 不携带）。
- AC8（诚实空态）：无匹配记录返回空列表 `items: []`，不抛错。
- AC9（契约不变）：既有 `GET /services/{id}/activities` 行为与契约不动。
- AC10（前端审计入口）：服务中心第二栏子导航新增"审计操作记录"（`/audit` 路由、运维模式壳、
  最左轨服务中心点亮）；AuditPage 过滤条（from/to、服务下拉、类型下拉、结果下拉）+ cursor
  分页列表 + 类型/结果/服务/会话/时间/脱敏摘要 + 详情跳转（run → `/workbench/sessions/:sid/runs/:rid`，
  action → `/workbench/approvals/:proposal_id`）；空态/失败态诚实展示；服务标题由既有
  services 查询映射、未知服务回退显示 service_id 原文。
- AC11（回归）：`test_service_center` / `test_p2_application_services` /
  `test_p5_controlled_action` 相关全绿；前端 `typecheck`/`test`/`build` 通过。
- 文档：`docs/接口清单.md` 第五部分审计标注已交付；`docs/路线图.md` 当前阶段登记本工作包。

### 明确不做

- 不做身份/审批人模型；不暴露演示占位身份 `local_operator`。
- 不做日志/Trace 原始事件检索；不暴露 CoT/Prompt/原始 SQL/原始工具输出/异常详情。
- 不做告警通知 / 导出 / 报表。
- 不新增持久化、无数据库迁移（复用 runs/proposals/action_events 既有表）。
- 不改变既有 `GET /services/{id}/activities` / 会话 / 审批 / SSE 契约与行为。
- 不做瞬时 action 事件（execution_requested/execution_started/precondition_checked/
  verification_started）入流；不做服务详情内审计子页。
- 无配置项/环境变量；无 Connector/凭据；审计检索纯只读、不触发目标服务连接。
- `docs/prd/` 不动；`data/`、`demo/` 不动；不触碰其他 Agent 的工作包文件。

## 切片拆分（2 个独立可验收切片）

- [ ] S1：后端审计检索 API——`src/domain/audit.py` + `audit_repositories.py` +
  `infrastructure/persistence/audit_repositories.py` + `application/audit_service.py` +
  `schemas/resources/cursors/routes/dependencies` + `tests/test_audit_api.py`。
  验收语义：AC1（跨服务跨会话分页，含同秒多行/跨表 id 序的交错数据）、AC2（时间窗与 422）、
  AC3（未知 service_id 空列表）、AC4（11 类型过滤）、AC5（10 结果过滤含 expired）、
  AC6（脱敏——事件 data 不整包透传）、AC7（approval_actor="未记录"）、AC8（空态）、AC9（契约不变）、
  AC11（回归）。
- [ ] S2：前端审计入口页——`client.ts`/`queries.ts`/`generated.ts`（generate:api）+
  `features/audit/AuditPage.tsx` + `App.tsx`/`GlobalNav.tsx`/`ServiceContextNav.tsx` +
  `AuditPage.test.tsx` + 接口清单/路线图文档更新。
  验收语义：AC10（入口可达、过滤可用、空态/失败态诚实、详情跳转）+ AC11 前端回归。

## 改动面（文件级）

### 后端（新增）

- `backend/src/domain/audit.py` —— `AuditActivityData` / `AuditActivityKind` / `AuditActivityType`
  （11 值）/ `AuditOutcome`（10 值 + 类型→结果映射）/ `AuditActivityCursor`。
- `backend/src/domain/audit_repositories.py` —— `AuditActivityRepository` 只读协议。
- `backend/src/infrastructure/persistence/audit_repositories.py` —— `SqlAlchemyAuditActivityRepository`：
  A/B 双查询（时间窗/service_id/类型/结果过滤 + 键集游标，各取 limit+1）+ Python 归并 +
  行→`AuditActivityData` 安全收敛（复用 `service_repositories.py` 的 `_as_*` 映射纪律）。
- `backend/src/application/audit_service.py` —— `AuditApplicationService.list_activities(query)`：
  窗口校验（from > to 明确错误）、过滤组装。
- `backend/tests/test_audit_api.py` —— AC1–AC9 服务端面 + 交错数据分页/边界。

### 后端（修改）

- `backend/src/api/v1/schemas.py` —— `AuditActivityResource` / `AuditActivityListResponse`。
- `backend/src/api/v1/resources.py` —— `audit_activity_resource()`（run/action 分型收敛 +
  事件 data 白名单提取 + 二次限长）。
- `backend/src/api/v1/cursors.py` —— `AuditActivityCursor` 编解码纳入。
- `backend/src/api/v1/routes.py` —— `GET /audit/activities` 路由（`parse_page_cursor` +
  `APPLICATION_ERROR_STATUS` 错误收敛）。
- `backend/src/api/v1/dependencies.py` —— `V1Services` 装配 `audit_service`
  （仅依赖 `session_factory`，无外部依赖，非可选）。

### 前端（新增 + 修改）

- `frontend/src/features/audit/AuditPage.tsx`（**新增**）+ `AuditPage.test.tsx`（**新增**）。
- `frontend/src/api/v1/generated.ts`（`npm run generate:api` 重新生成，禁止手编）。
- `frontend/src/api/v1/client.ts`：`list_audit_activities`；`queries.ts`：`audit_activities` key/query。
- `frontend/src/app/App.tsx`：`/audit` 路由 + `is_operations`。
- `frontend/src/features/shell/GlobalNav.tsx`：`/audit` 点亮服务中心。
- `frontend/src/features/shell/ServiceContextNav.tsx`：第二栏"审计操作记录"入口项。

### 文档

- `docs/接口清单.md`（第五部分审计标注已交付）、`docs/路线图.md`（当前阶段登记）、
  `docs/workpack/README.md`（本工作包活跃登记）。

### 明确无改动

- 无数据库迁移（复用既有三表）；无配置项/环境变量；无 Connector/凭据/真实连接；
  SSE 与 Run 执行链路、审批执行链、多 Agent 内核不动；`docs/prd/` 不动。

## 验证方法

- 后端（在 worktree `backend/` 下执行，使用 worktree 内重建的 venv）：
  - 聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_audit_api.py -q`
  - 回归：`..\.venv\Scripts\python.exe -m pytest tests/test_service_center.py tests/test_p2_application_services.py tests/test_p5_controlled_action.py tests/test_api.py tests/test_p2_api_v1.py -q`
  - 提交前跑全量 `..\.venv\Scripts\python.exe -m pytest tests -q`
- 前端（在 worktree `frontend/` 下执行）：`npm run typecheck`、`npm run test`、`npm run build`。
- API 契约：后端起 8000 → `npm run generate:api` 重新生成 generated.ts；
  8000 被占用时用 OpenAPI 落盘方式（`python -c "from src.app import app; import json; json.dump(app.openapi(), open('openapi.json','w'))"` + `npx openapi-typescript openapi.json -o src/api/v1/generated.ts`）。
- 门禁：`git diff --check`；只暂存本工作包文件，禁止 `git add .`；检查敏感字面量。

## 提交计划

- S1 后端审计检索 API：
  `feat: 审计操作记录——跨服务跨会话活动检索 API（P8，issue #62）`
- S2 前端审计页：
  `feat: 审计操作记录页——入口、过滤与详情跳转（P8，issue #62）`
- 每个切片完成后集中 Test → 独立子代理 Review → 提交；全部完成后经
  `dev-deliver`（fetch+merge main → push → PR → 合并 → 归档）。
