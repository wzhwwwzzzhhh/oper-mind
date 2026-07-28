# P3 独立审查 — 主前端工作台

> 日期：2026-07-28　|　结论：✅ P3.3 Design 通过；等待 P3.3a 实现授权
>
> 审查基线：`87c4f83 docs: 完成P3.2c2离线前置核对`　|　工作分支：`feat/p3-workbench`

## 1. 审查范围

本次为 P3.3 的独立设计审查：核实 P2 Run 受理、幂等、RunEvent、持久化 SSE 和刷新恢复契约；审查前端 Step 拆分、真实数据库延后决策、`frontend/`/`report/` 边界、错误与空状态。未执行任何前端业务代码、后端改动、真实 DB 连接、在线迁移或运行时资产写入。

## 2. 审查依据

- API 合同：`docs/开发/P0-V1产品化基线/api-v1-contract.md:426-503`；
- 后端既有实现：`backend/src/api/v1/routes.py:313-429`、`backend/src/api/v1/sse.py:20-65`；
- P2 完成快照：`docs/开发/P2-会话诊断闭环/HANDOFF.md:8-32`、`review.md:89-116`；
- 现有 P3 读模型与 client：`frontend/src/api/v1/client.ts:88-108,199-260`、`frontend/src/api/v1/queries.ts`、`frontend/src/features/workbench/WorkbenchPage.tsx`；
- P3.2 离线接入门槛：`docs/开发/P3-主前端工作台/step2c2-真实读模型前置条件核对.md`。

## 3. 独立审查结果

| 检查项 | 结论 | 审查结果 |
|---|---|---|
| Run 受理契约 | 通过 | 设计固定为 `POST /sessions/{session_id}/runs`、必填 UUID `Idempotency-Key`、`202` 后以响应 Run 为准；没有调用旧 `/diagnose` |
| 幂等与未知网络结果 | 通过 | 同一逻辑请求稳定复用 key/query；编辑或明确新请求才换 key；刷新不自动 POST；`409` 不自动换 key |
| request/trace 关联 | 通过 | JSON POST 延续 `X-Request-Id` 与 headers/meta 核对；Run 的 trace 取自响应；SSE 只从 envelope meta 消费安全关联 |
| 事件与 SSE | 通过，已修正风险 | 事件按 `(run_id, sequence)` 去重、按 sequence 排序；终态重读 Run；纠正了 EventSource 初连携带 `after_sequence` 会与自动重连 Last-Event-ID 冲突的设计缺陷，固定初连不带 query cursor |
| 刷新/断线/错误 | 通过 | 恢复顺序为 Session → Runs → Message → Run → Events → 非终态 SSE；网络/SSE 失败不伪造成 Run failed；REST cursor 错误从首个可用页重新同步 |
| P3/P4/P5/P6 边界 | 通过 | P3.3 仅做受理和过程摘要；结果卡留 P3.4，真实连接器/环境/告警/审批/知识/报告均不提前实现 |
| `frontend/`/`report/` 边界 | 通过 | 只规划 `frontend/` 既有工程；不改、不嵌入、不复用 `report/`，P6 前无 Trace deep-link |
| 真实数据与运行时资产 | 通过 | 用户已决定真实 DB 验收后置；C1–C8 保留；本设计不连接 8000/真实 DB、不运行 Alembic、不创建 SQLite |
| Step 可控性 | 通过 | P3.3a（受理）→ P3.3b（事件/SSE）→ P3.3c（独立 mock 验收）分开 Review/Commit，避免一次混入协议、实时连接和人工联调 |
| 文档与唯一下一步 | 通过 | A/B Plan、规则镜像、P3 design/step/review/HANDOFF 都应同步为 P3.3 Design 完成，唯一下一步 P3.3a |

## 4. 已知风险与非目标

1. P2 SSE 是持久化事件短连接轮询，不是生产级消息总线；高吞吐、慢客户端、崩溃接管、重试策略与保留策略仍属于 P7。
2. EventSource 首连从最早事件重放并由客户端去重，可能在长事件历史下增加读取量；这是现有 P2 双游标契约下避免自动重连冲突的正确性优先选择。性能优化须先另做协议设计。
3. P2 cursor 尚未绑定 Session scope；P3.3 以 Query key/生命周期隔离避免前端误用，但后端统一 scope/授权仍待后续收口。
4. 无认证/RBAC、无真实 DB/数据源验收；用户后续接入时仍必须重新确认 C1–C8，且真实失败不能降级为 mock。

## 5. 结论与唯一下一步

P3.3 Design 通过独立审查。设计准确消费 P2 v1 Run、幂等、RunEvent 与持久化 SSE 契约，并将 EventSource 双游标冲突风险在实现前消除。未发现阻塞 P3.3a 的文档或范围矛盾。

**当前唯一下一步：P3.3a：Run 受理与幂等重试实现。**开始前应按恢复流程核对隔离改动；本轮设计文档不自动暂存或提交，等待用户明确授权。