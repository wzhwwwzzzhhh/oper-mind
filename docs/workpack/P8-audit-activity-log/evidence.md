# P8-audit-activity-log · AC 证据表

> 本表由 dev-execute 逐步回写；每条 AC 附代码/接口/测试证据与通过状态。

## S1 后端审计检索 API（AC1–AC9、AC11）

| AC | 验收标准 | 证据 | 状态 |
|---|---|---|---|
| AC1 | 跨会话跨服务审计活动安全摘要分页列表 | `GET /api/v1/audit/activities` 路由（`routes.py:list_audit_activities`）+ 双源归并仓储（`audit_repositories.py:SqlAlchemyAuditActivityRepository`）+ `tests/test_audit_api.py::test_跨服务跨会话返回审计活动分页列表`、`test_分页游标跨页无重复无遗漏` | ✅ |
| AC2 | 时间窗 from/to 过滤；非法窗口明确错误 | 路由 from/to 透传 + `from > to → 422 VALIDATION_ERROR`；`test_时间窗过滤` | ✅ |
| AC3 | service_id 过滤；未知 ID 空列表不抛错 | 按 `DiagnosisRunRecord.service_id` 过滤（覆盖 P6 多服务会话，`test_多服务会话按Run服务归属过滤`）；`test_服务过滤与未知服务空列表` | ✅ |
| AC4 | 动作类型过滤覆盖调查 Run 与受控动作 | `AuditActivityType` 11 值枚举（`domain/audit.py`）；`test_类型过滤覆盖Run与action两类`（含瞬时事件 422） | ✅ |
| AC5 | 结果状态过滤 | `AuditOutcome` 10 值（含 expired，approval_recorded/action_failed 按事件 data.status 派生）；`test_结果过滤` | ✅ |
| AC6 | 摘要不含证据原文/工具输出/SQL/异常/凭据 | 事件 data 只提取白名单字段（summary/mode/action_id/status），绝不整包透传；`test_瞬时事件不入流且事件data非白名单字段不透传` | ✅ |
| AC7 | 审批人如实标注"未记录" | `approval_actor="未记录"` 仅 approval_recorded 项（`APPROVAL_ACTOR_UNRECORDED`）；`test_审批人字段如实标注未记录` | ✅ |
| AC8 | 无匹配记录空列表不抛错 | `test_无匹配记录返回空列表` | ✅ |
| AC9 | 既有 `GET /services/{id}/activities` 契约不变 | `test_既有服务活动契约不变`；回归 `test_p4_service_center.py` 全绿 | ✅ |
| AC11 | 回归 | 聚焦 + 回归套件 36 passed；全量 `tests -q` 见下方记录 | ✅ |

### 验证记录（S1）

- 聚焦：`pytest tests/test_audit_api.py -q` → **15 passed**（2026-08-12，含审查后新增的组合过滤交集测试）
- 回归：`pytest tests/test_p4_service_center.py tests/test_p2_application_services.py tests/test_p5_controlled_action.py tests/test_api.py tests/test_p2_api_v1.py -q` → 36 passed
- 全量：`pytest tests -q` → **414 passed**（2026-08-12，审查 P2 修复后重跑）
- `git diff --check` → 干净
- 独立审查：review.md PASS（P2 组合过滤语义已修复；P3 项均为对齐既有模式或已记录偏差）
- 实现说明：`audit_service` 以可选字段 + 路由守卫装配进 `V1Services`（对齐 `action_service`/`service_center` 既有模式；生产装配恒非空，旧测试装配安全拒绝）

## S2 前端审计入口页（AC10）

| AC | 验收标准 | 证据 | 状态 |
|---|---|---|---|
| AC10 | 前端审计入口可访问、支持过滤、空态/失败态诚实；typecheck/test/build 通过 | `AuditPage.tsx`（/audit 路由 + 过滤条 + 分页列表 + 跳转）+ `App.tsx`/`GlobalNav.tsx`/`ServiceContextNav.tsx` 接线 + `AuditPage.test.tsx`（7 用例：入口/列表/审批人"未记录"/空态/失败态/过滤参数/跳转）；浏览器实测（Playwright）：入口、列表、类型过滤、行跳转均正常 | ✅ |

### 验证记录（S2）

- `npm run typecheck` → 通过；`npm run build` → 通过（tsc -b + vite build）
- `npm run test` → **120 passed**（16 文件，含 AuditPage 7 用例）
- 浏览器实测（2026-08-12）：真实后端（8000）+ 种子数据 + vite（5174）→ `/audit` 页面渲染 7 行活动（run + action、服务标题、会话、时间、脱敏摘要）、审批人"未记录"、未绑定服务行、类型过滤"调查失败"只余 1 行、点击审批行跳转提案详情页；唯一 console 错误为 favicon 404（dev 噪音）
- 文档：`docs/接口清单.md`（第五部分审计标注已交付 + 汇总表同步 v1 合计 42）、`docs/路线图.md`（当前阶段登记审计工作包）
- `git diff --check` → 干净
- 合并 main（2026-08-12）：合并 #68（模型列表探测）后解 `docs/接口清单.md` 冲突（计数同步 v1 合计 42、模型设置 9）；合并后复验：后端 audit + model_provider 66 passed、前端 typecheck + 123 passed 全绿
