# P8-workbench-loop-closure · 独立实现审查

> 更新：2026-08-10
> 审查者：只读独立子代理（dev-execute Phase 4），基线 main@88673f7，分支 3 个功能提交 + 文档改动。
> 结论：**PASS**（无 P0/P1；P2/P3 已按审查意见修正或在收尾提交中处理）

## 独立验证

- 后端全量 `pytest tests -q` → 366 passed；聚焦 29 项全绿；`mypy` 13 源文件 no issues。
- 前端 `typecheck` ✅、`vitest` 105 passed（14 files）✅、`build` ✅；`git diff --check` 干净。
- diff 全文无 `sk-`/凭据/裸 except/新增生产 print；`产品定义.md`、`开发规范.md`、`架构与开发路径.md` 未被改动。

## 发现与处置

- [P2] 前端投影：无前驱的普通回复会被静默丢弃/可能错配 → **已修复**：
  `conversation-turns.ts` 将未配对的 `plain_replies` 作为独立 `plain_reply` 时间线项展示，
  并补单测「无前驱的普通回复作为独立回复展示而不静默丢弃」。
- [P3] `docs/接口清单.md` 摘要接线数自相矛盾 → **已修正**：会话工作台 19 个路由、未接线 2
  （PATCH/DELETE sessions），v1 合计 35 / 前端已接线 33。
- [P3] 前端 `is_investigation_message` 预分流与 Design §2.5「先调 messages 再回退」字面有偏差 → **已接受**：
  关键词集合与后端 `requires_database_context` 逐一一致、409 兜底仍在，服务端仍权威；
  已在 Design §2.5 如实更新实现说明。
- [P3] `plain_messages.py` 复用 `services.py` 私有 `_in_transaction`/`_touch_session` → 记录为已知风格项，
  同层应用模块内复用可接受，未扩范围。
- [P3] `ActionProposalSummaryResource.action_id/mode` 用 `Literal` + `cast` 硬编码唯一动作 → 与既有
  detail 资源同一模式（当前唯一动作无实害），记录为后续扩展待办。
- [P3] 意图判定未做 try/except 防御（纯字符串匹配不会抛）→ 记录为已满足语义，缺防御代码。
- [P3] 收尾状态：plan.md 勾选框、workpack README、PRD/接口清单状态 → 收尾提交时已同步。

## AC 证据表

| AC | 证据 | 结果 |
|---|---|---|
| AC1 普通消息轻量回复、不创建 Run | `test_普通消息返回轻量回复且不创建Run`（201 + 双消息 run_id=null + runs 为空） | PASS |
| AC2 调查意图走既有 Run 主链路 | `test_调查意图消息返回409` + 既有受理/幂等回归全绿 + 前端 409 回退 | PASS |
| AC3 回复明确「未启动调查」 | `test_助手回复内容为确定性模板且不含伪造结果` | PASS |
| AC4 queued/running 可取消、写事件、后台终止 | `test_run_cancel.py` 四用例（queued/running 取消、queued 取消后不启动、检查点停止追加） | PASS |
| AC5 已结束 409 且状态不变 | `test_已成功/已失败Run取消返回错误` + API 409 | PASS |
| AC6 重复取消幂等 | `test_重复取消同一Run幂等`（事件一次）+ API 二次 204 | PASS |
| AC7 全局提案安全摘要分页 | `test_提案列表返回安全摘要…`、`test_提案列表按创建时间倒序分页` | PASS |
| AC8 状态过滤只返回匹配项 | `test_提案列表状态过滤只返回匹配项` + 422 | PASS |
| AC9 列表不含证据原文/未脱敏字段 | 白名单键集合断言 + 禁 7 类字段 | PASS |
| AC10 前端待审批入口 + 进入审批 | `ApprovalsPage.test.tsx` + App 入口/详情/停止按钮 | PASS |
| AC11 回归全绿 + 前端三件套 | 后端 366、mypy 0、前端 typecheck/105 test/build、diff --check | PASS |

## 结论

PASS —— 实现与 plan/PRD/Design 映射完整，AC1–AC11 全部可复现通过，P0 安全红线零命中，
`POST /sessions/{id}/runs` 主链路与 `GET /sessions/{id}/messages` 契约未被破坏。
