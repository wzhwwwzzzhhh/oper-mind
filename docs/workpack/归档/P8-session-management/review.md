# 工作包审查：P8-session-management

> 审查方式：独立只读子代理（general-purpose，禁止写文件/改代码）
> 审查日期：2026-08-12
> 审查输入：plan.md、PRD（AC1–AC10）、已确认 Design、实现 diff、新增测试文件、基线文档

## 总体：PASS

实现与 plan/PRD/Design 一致，AC1–AC10 全部有代码与测试证据，安全脱敏、契约兼容与架构复用均正确。无 P0/P1/P2。

## 发现（P3，均已修复）

- [P3] `frontend/src/test/handlers.ts` 的 `/api/v1/services` handler 残留调试 `console.log('SERVICES REQ', ...)` → 已删除。
- [P3] `docs/接口清单.md` 内部不一致（汇总表欠账未更新、`已有（16）`、`GET /sessions` 行仍标"无搜索"、路由计数 35）→ 已同步：汇总"会话工作台 20 / 2"、`已有（20）`、`GET /sessions` ✅ 含 q 搜索、v1 合计 41 / 已接线 39。
- [P3] RunsPage「加载更多」分页按钮无前端测试（MSW 恒返回 `has_more:false`）→ 不在 plan 测试清单内，后端分页已有完整测试，接受。

## 重点核对结论

- `GET /runs` 与 `GET /runs/{run_id}` 路径形状不同，无路由冲突。
- 无 `q` 时 `GET /sessions` 仅多传 `None` 参数，契约不变（AC6）。
- `SessionRecord.title.contains(q, autoescape=True)` 字面转义正确（`%`/`_` 不作通配符）。
- `_safe_run_error` 白名单仅在 `status==failed` 时映射，未知错误文本收敛为通用摘要（AC4）。
- cursor 复用 `parse_page_cursor` / `DiagnosisRunCursor` / `_page` / `_validate_limit`，无重复建设。
- `_global_run_data` 对行做类型防御；`q` 校验 strip 后非空 + 控制字符（<0x20、0x7F）+ 长度 ≤100 → 422（AC7）。
- 无迁移/配置/Connector/凭据改动；`generated.ts` 与路由一致；前端跨层走既有 client/queries/resource-readers 模式。
- `完善清单.md` P1-12 如实标 ⏳（E2E 复验待办），符合开发规范 §7.3。

## AC 证据表

| AC | 证据（代码/测试/命令） | 结论 |
|---|---|---|
| AC1 | `routes.py` `list_runs` + `repositories.py` `list_page`（跨会话 join 标题、created_at 倒序、limit+1）；`test_runs_list.py` 跨会话跨服务摘要分页 | PASS |
| AC2 | status 过滤（RunStatus Literal，非法 422）；`test_runs_list.py` 状态过滤 | PASS |
| AC3 | Run 自身 service_id 精确匹配，不存在值空列表；`test_runs_list.py` 服务过滤 | PASS |
| AC4 | 查询仅选白名单列 + `_safe_run_error` 白名单；`test_runs_list.py` 字段集精确断言 + 含凭据错误文本收敛 | PASS |
| AC5 | q 标题 LIKE 字面匹配（autoescape）；`test_session_search.py` 匹配/无匹配/通配符字面 | PASS |
| AC6 | 无 q 行为不变；`test_session_search.py` 无 q 契约测试 | PASS |
| AC7 | 超长/控制字符/纯空白 → 422；`test_session_search.py` 非法关键词 | PASS |
| AC8 | `Sidebar.tsx` 搜索框 + document 级 Ctrl+K + Esc 清空；`Sidebar.test.tsx` 聚焦/搜索/空态/Esc/失败提示 | PASS |
| AC9 | 最近调查入口 + `RunsPage`（状态标签/服务下拉/分页/空态/跳转详情）；`RunsPage.test.tsx` | PASS |
| AC10 | 后端全量 414 passed；前端 124 passed + typecheck + build；`App.test.tsx` 文本域断言收窄至 main 区（适配侧栏搜索框） | PASS |
