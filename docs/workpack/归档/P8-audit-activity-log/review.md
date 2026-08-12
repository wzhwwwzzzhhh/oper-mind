# P8-audit-activity-log · S1 独立审查结论

> 审查日期：2026-08-12（dev-execute Phase 4 独立只读子代理）
> 结论：**PASS**（无 P0/P1）；1 项 P2 已修复并复验。

## 发现

- [P2] **类型与结果组合过滤语义不一致**（已修复）：action 侧 `outcome` 派生的事件类型会覆盖显式传入的 `action_type`（如 `action_type=action_blocked&result=approved` 会返回 approval_recorded 行），Run 侧为交集语义。修复：`_list_action_items` 改为交集——显式类型与结果派生类型不一致时返回空；补 `test_类型与结果组合过滤取交集`。
- [P3] `_audit_service` 守卫复用 `ServiceCenterUnavailableError`（对齐既有 `_service_center` 模式，仅旧测试装配防御路径）。
- [P3] `from > to` 时区不一致边界未文档化（monitor 端点同暴露，不新增）。
- [P3] Run 侧 summary 无长度约束（与既有 `ServiceActivityData` 同构暴露，不新增风险）。
- [P3] 跨模块导入 `service_repositories._as_*` 私有助手（plan 明示的复用纪律）。
- [P3] `audit_service` 实现为可选+守卫而非 plan 所述"非可选"（evidence.md 已如实记录，与 action_service/service_center 既有装配一致）。

## AC 证据表（S1 范围）

| AC | 结论 | 证据 |
|---|---|---|
| AC1 | PASS | 双源归并 + 键集游标；同秒跨表分页测试无重复无遗漏；跨服务跨会话列表测试 |
| AC2 | PASS | 时间窗过滤 + `from > to` → 422 |
| AC3 | PASS | 按 Run 权威 service_id 过滤；未知 ID 200 空列表；P6 多服务会话测试 |
| AC4 | PASS | 11 值类型枚举；SQL 侧过滤；瞬时事件/非法值 422；组合过滤交集（修复后） |
| AC5 | PASS | 10 值结果；approval_recorded/action_failed 按 data.status 派生（与落库事实一致）；expired 覆盖 |
| AC6 | PASS | 事件 data 只提取白名单字段；测试断言 sk-/evidence/sql 不出现 |
| AC7 | PASS | approval_actor="未记录" 仅 approval_recorded |
| AC8 | PASS | 空库/无匹配 200 空列表 |
| AC9 | PASS | 未触碰既有路由；test_p4_service_center 回归绿 |
| AC11 | PASS | 聚焦 15 passed；回归 36 passed；全量套件见 evidence.md |

## 结论

PASS。安全边界核验：无凭据/DSN/`sk-` 进响应与日志；无裸 except/生产 print；中文注释、类型标注齐全；纯只读、无迁移、无越界文件（改动面与 plan.md 一致）。
