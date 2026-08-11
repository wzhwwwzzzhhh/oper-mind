# P8-workbench-loop-closure · AC 证据表

> 更新：2026-08-10（S1/S2/S3 全绿后回写）
> 分支：`feat/p8-workbench-loop-closure`；worktree：`D:/market-handsome/oper-mind-worktrees/p8-workbench-loop-closure`

## 验证命令（已执行并全绿）

- 后端全量：`backend/` 下 `..\.venv\Scripts\python.exe -m pytest tests -q` → **366 passed**
- 后端聚焦：`test_plain_message_api.py`、`test_run_cancel.py`、`test_action_proposal_list.py`、
  `test_p43_service_context.py` 全部通过
- 后端类型：`mypy`（涉及 13 个源文件）→ no issues
- 前端：`npm run typecheck` ✅、`npm run test` → **105 passed（14 files）**、`npm run build` ✅
- 门禁：`git diff --check` 干净

## AC 证据表

| AC | 验证方式 | 证据 | 结果 |
|---|---|---|---|
| AC1 普通消息只回普通回复、不创建 Run | 后端 API 测试 | `test_plain_message_api.py::test_普通消息返回轻量回复且不创建Run`（201 + user/assistant 双消息 + runs 为空） | PASS |
| AC2 调查意图走既有 Run 主链路 | 后端 API 测试 + 回归 | `test_调查意图消息返回409`（服务端判定）+ 既有 `test_p43_service_context.py`/Run 受理测试全绿 | PASS |
| AC3 回复明确说明「未启动调查」 | 后端 API 测试 | `test_助手回复内容为确定性模板且不含伪造结果`（`PLAIN_REPLY_TEMPLATE` 含「未启动调查」「慢查询/连接池/索引」引导） | PASS |
| AC4 queued/running 可取消、写取消事件、后台终止 | 应用服务测试 | `test_run_cancel.py`：`test_取消queued运行中的Run…`、`test_取消running运行中的Run…`、`test_queued取消后execute_run不再启动执行`、`test_执行中取消后事件循环停止追加` | PASS |
| AC5 已结束 Run 不可取消返回 409 | 应用服务 + API 测试 | `test_已成功Run取消返回错误且状态不变`、`test_已失败Run取消返回错误`、`test_取消接口对已成功Run返回409` | PASS |
| AC6 重复取消幂等 | 应用服务 + API 测试 | `test_重复取消同一Run幂等`（事件只写一次）、`test_取消接口对queuedRun返回204`（二次 204） | PASS |
| AC7 全局提案安全摘要分页 | API 测试 | `test_提案列表返回安全摘要…`、`test_提案列表按创建时间倒序分页` | PASS |
| AC8 状态过滤只返回匹配项 | API 测试 | `test_提案列表状态过滤只返回匹配项`、`test_非法状态过滤返回422` | PASS |
| AC9 列表不含证据原文/未脱敏字段 | API 测试 | `test_提案列表返回安全摘要且不含证据原文`（白名单字段断言 + 禁 description/target/evidence_ids/digest 等） | PASS |
| AC10 前端待审批入口 + 进入审批 | 前端交互测试 | `ApprovalsPage.test.tsx`、`App.test.tsx::待审批入口导航到提案列表`、`待审批列表进入提案详情并复用审批面板`、`运行中的调查可点击停止并取消 Run` | PASS |
| AC11 回归全绿 + 前端三件套 | 全量回归 | 后端 366 passed；前端 typecheck/test(105)/build 全绿；`git diff --check` 干净 | PASS |

## 切片提交

| 提交 | 内容 | 状态 |
|---|---|---|
| `0c7fcb0` | S1 独立消息通道（后端） | 已提交 |
| `15b6789` | S2 取消 Run + 全局提案列表（后端） | 已提交 |
| `8d88f1a` | S3 会话工作台闭环前端适配 | 已提交 |
| （待交付） | 文档收尾（Design/接口清单/路线图/本证据表） | 随 PR 提交 |
