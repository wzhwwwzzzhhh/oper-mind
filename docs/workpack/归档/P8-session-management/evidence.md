# P8-session-management · AC 证据表

> 验证日期：2026-08-12（worktree `feat/p8-session-management`）

## 验证记录

- 后端聚焦：`pytest tests/test_runs_list.py tests/test_session_search.py -q` → **15 passed**
- 后端回归：`pytest tests/test_api.py tests/test_p2_api_v1.py tests/test_p2_repositories.py -q` → **18 passed**
- 后端全量：`pytest tests -q` → **414 passed**
- 前端：`npm run test` → **124 passed（17 文件）**；`npm run typecheck` → 通过；`npm run build` → 通过
- 门禁：`git diff --check` → 干净（exit 0）
- API 契约：OpenAPI dump → `openapi-typescript` 重新生成 `generated.ts`（禁止手编，已核对 `list_runs` 与 `q` 参数入类型）

## AC 证据

| AC | 结论 | 证据 |
|---|---|---|
| AC1 跨会话跨服务 Run 安全摘要分页 | PASS | `GET /runs`（routes.py）；`SqlAlchemyDiagnosisRunRepository.list_page`（repositories.py，JOIN SessionRecord 取标题，created_at 倒序，limit+1）；`test_runs_list.py::test_跨会话跨服务返回安全摘要分页列表` |
| AC2 状态过滤只返回匹配 Run | PASS | 路由 `status: RunStatus | None`（非法 422）；`test_runs_list.py::test_状态过滤只返回匹配状态的Run` |
| AC3 service_id 过滤；不存在值空列表 | PASS | 按 Run 自身 service_id 精确匹配；`test_runs_list.py::test_服务过滤只返回该服务的Run且不存在服务返回空列表` |
| AC4 摘要无证据原文/工具输出/CoT/凭据 | PASS | 查询仅选白名单列；`_safe_run_error` 白名单映射（未知错误收敛为通用摘要）；`test_runs_list.py::test_摘要字段白名单且失败错误经白名单映射`、`test_非白名单错误文本被收敛为通用摘要`（含 DSN 文本收敛断言） |
| AC5 q 标题匹配，无匹配空列表 | PASS | `SessionRecord.title.contains(q, autoescape=True)`；`test_session_search.py::test_标题关键词只返回匹配会话`、`test_无匹配返回空列表`、`test_关键词通配符按字面匹配` |
| AC6 无 q 行为与既有契约一致 | PASS | q 为可选参数，None 时查询不变；`test_session_search.py::test_不带q行为与既有契约一致` |
| AC7 非法关键词明确错误 | PASS | `Query(min_length=1, max_length=100)` + `_validate_session_search_query`（控制字符/空白 → 422 VALIDATION_ERROR）；`test_session_search.py::test_非法关键词返回明确错误` |
| AC8 侧栏搜索框 + Ctrl K 真实可用 | PASS | `Sidebar.tsx`：搜索框（300ms debounce 服务端搜索）+ document 级 Ctrl+K 聚焦（preventDefault）+ Esc 清空；`Sidebar.test.tsx` 5 例（聚焦/搜索/空态/Esc/失败提示） |
| AC9 最近调查入口展示全局 Run 列表 | PASS | Sidebar「最近调查」入口 → `/workbench/runs`；`RunsPage.tsx`（状态标签 + 服务下拉 + cursor 分页 + 行点击进既有 Run 详情）；`RunsPage.test.tsx` 5 例 |
| AC10 回归 | PASS | 后端 414 passed（含 test_api.py / test_p2_api_v1.py）；前端 124 passed + typecheck + build；`App.test.tsx` 两处断言适配（文本域收窄至 main 区） |

## 未做 / 待办

- `完善清单.md` P1-12 标 ⏳：Ctrl K 已实现并有交互测试，浏览器端到端复验待办（复验后标 ✅）。
- RunsPage「加载更多」按钮无前端测试（MSW 恒 `has_more:false`）；后端 cursor 分页已有完整测试覆盖。
