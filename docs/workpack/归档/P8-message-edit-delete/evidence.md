# P8-message-edit-delete · AC 证据表

> PRD：`docs/prd/session/P8-message-edit-delete.md`（进行中，issue #75）
> Design：`docs/design/session/P8消息编辑与删除Design.md`（已确认）
> 分支：`feat/P8-message-edit-delete`；提交：`cdf8d9b`（docs）、`f441272`（S1 后端）、`9f29805`（S2/S3 前端）

## AC 证据

| AC | 验收标准 | 证据（代码/测试/命令） | 结果 |
|---|---|---|---|
| AC1 | PATCH 编辑 user 消息：更新内容、返回含 edited_at、时间线位置不变 | `test_message_edit_delete_api.py::test_编辑user消息返回更新后内容与edited_at且时间线不变`；repository 测试 `test_message_repository_编辑软删与列表过滤`（created_at 不变断言） | ✅ PASS |
| AC2 | PATCH 编辑 assistant/system 消息 → 明确错误（422），消息不变 | `test_编辑assistant消息返回422且消息不变`（MESSAGE_NOT_EDITABLE，内容/edited_at 不变断言） | ✅ PASS |
| AC3 | PATCH 不存在的消息 / 不属于该会话 → 404 | `test_编辑不存在的消息或不属于该会话返回404` | ✅ PASS |
| AC4 | PATCH 空内容 / 超长内容 → 422 | `test_编辑空内容或超长内容返回422`（空白 422、4001 字 422） | ✅ PASS |
| AC5 | DELETE user 消息 → 204，列表不再出现 | `test_删除user消息返回204且列表不再出现` | ✅ PASS |
| AC6 | DELETE assistant/system 消息 → 明确错误（422），消息保留 | `test_删除assistant消息返回422且消息保留`（MESSAGE_NOT_DELETABLE） | ✅ PASS |
| AC7 | 删除 Run 关联消息不影响 Run 详情与留痕 | `test_删除与Run关联的消息不影响Run详情与历史留痕`：删除输入消息后 `execute_run` 仍成功（_claim_run 可读软删消息）、Run 详情 input_message_id 不变（arch-review P2 回归落地） | ✅ PASS |
| AC8 | 重复删除幂等（204），无错误副作用 | `test_重复删除同一消息幂等返回204`；repository 测试 archive 二次返回 False | ✅ PASS |
| AC9 | 前端编辑后展示"已编辑"；删除后消息消失，空态/失败态诚实展示 | `App.test.tsx`：`编辑用户消息后刷新列表并展示已编辑标注`、`删除用户消息后消息消失且调查卡片保留可追溯`（占位"（问题已删除）"、Run 卡片保留）、`删除失败如实提示且消息保留`；投影测试 `读取 edited_at 字段`、`输入消息已删除的调查卡片保留展示`、`输入已删除的调查按创建时间插入时间线对应位置` | ✅ PASS |
| AC10 | 回归：既有 test_api.py / 会话消息相关测试全绿；前端 typecheck/test/build 通过 | 后端全量 `pytest tests -q`：**502 passed, 2 skipped**（含 test_api.py、test_plain_message_api.py、test_run_rerun.py、test_p2_recovery_closure.py 等）；前端 `typecheck` ✅、`build` ✅、`vitest run`（本工作包相关文件全绿；详见下方说明） | ✅ PASS（有说明） |

## 验证记录

### 后端（worktree 内 `backend/`，`..\.venv\Scripts\python.exe`）

| 命令 | 结果 |
|---|---|
| `pytest tests/test_message_edit_delete_api.py -q` | 13 passed |
| `pytest tests/test_p2_repositories.py -q` | 7 passed（含新增 repository 测试） |
| `pytest tests/test_run_rerun.py -q` | 13 passed（迁移链回滚语义不受影响） |
| `pytest tests/test_plain_message_api.py tests/test_p2_application_services.py tests/test_p2_recovery_closure.py -q` | 全绿 |
| `pytest tests -q`（全量） | **502 passed, 2 skipped** |
| 迁移往返（临时库）`upgrade head → downgrade 20260812_12 → upgrade head` | 0/0/0（含 SQLite 外键重建保护） |
| `ruff check`（本工作包新增/修改文件） | All checks passed |

### 前端（worktree 内 `frontend/`）

| 命令 | 结果 |
|---|---|
| `npm run typecheck` | ✅ 通过 |
| `npm run build` | ✅ 通过 |
| `npx vitest run src/features/workbench/conversation-turns.test.ts` | 12 passed |
| `npx vitest run src/app/App.test.tsx`（含 3 个新交互测试） | 34 passed / 2 failed |
| `npm run test`（全量） | 142 passed / 7 failed（见说明） |

### 已知问题（与本工作包无关的既有环境 flake）

- `App.test.tsx` 的 2–3 个既有测试（`运行中的调查可点击停止并取消 Run`、`未结束调查不提供重新生成按钮`，
  以及偶发的 `重新生成失败如实提示且不影响原调查`）在本机（Windows + 本 vitest 版本）
  **基线 main 同样失败**（已用 `git stash` 回基线复现验证），表现为 running/queued 调查的
  会话主区未在 1s 内渲染完成，属时序性环境问题，与本工作包改动无关；失败集合随运行抖动。
  本工作包 3 个新增交互测试与 12 个投影测试全部通过。
- 全量 `vitest run` 并行时的 4 个无关文件测试（监控概览/知识库/提案/会话空态）单文件跑全绿，
  并行时偶发超时，属资源竞争 flake，与本工作包改动无关。

## 门禁检查

- `git diff --check`：干净 ✅
- 凭据/`sk-`/DSN/证据原文检查：本工作包未引入任何凭据、连接串或证据原文字段 ✅
- 提交范围：仅本工作包文件（docs/design、docs/workpack、docs/prd 状态、backend 12 文件、frontend 9 文件）✅
