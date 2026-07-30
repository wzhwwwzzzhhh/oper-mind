> **封存说明（2026-07-29）**：本 Review 仅记录个人会话路线的历史审查。当前开发入口为 `治理-DevOps-Copilot-MVP重定位/`，不得据此继续 P3.6 后续实现。
# R1 / P3.5–P3.6b.1 个人会话主体验 — 独立审查

> 审查日期：2026-07-29　|　结论：✅ P3.6b.1 Code/Test/Review 与用户边界验收均通过，由本提交收口。
>
> P3.6a 已提交为 `eb664dd feat: 完成P3.6a会话壳与只读Turn投影`，并已通过用户人工验收。

## 审查范围

- active Session 的调查型发送是否准确消费 P2 `POST /sessions/{id}/runs`；
- 稳定 `Idempotency-Key`、网络未知、202、409/422/归档错误是否不伪造事实；
- `input_message_id`、Runs / Messages cursor 对账是否防止 optimistic Turn；
- P3.6b.1 是否没有提前引入 SSE、多 Run 流恢复、Mock API、后端、真实资源或 P4/P5/P6 能力；
- 测试、构建、计划、交接与镜像规则是否一致。

## 独立核对结果

| 审查项 | 结论 |
|---|---|
| 调查型而非普通聊天 | 通过：仅 active Session 出现“发起调查”；文案明确每次提交会创建一次运维调查，未新增 Message API。 |
| POST / 202 | 通过：复用 generated P2 client / mutation；测试核验 POST query 与 UUID `Idempotency-Key`，只接受当前 Session 的合法 Run / input_message_id。 |
| 稳定意图 | 通过：意图在 POST 前写入 tab 限定 sessionStorage；网络错误后同 key 重试；不写入 token、Trace、events、Result、服务端异常或 URL。 |
| 409 冲突 | 通过：`IDEMPOTENCY_KEY_REUSED` 禁止编辑/发送，不自动换 key；必须显式丢弃意图。 |
| 422 / archived | 通过：validation 清除本地 intent 以便编辑重试；`SESSION_ARCHIVED` 触发 Session 重读，archived 本身无输入。 |
| 202 后事实 | 通过：不插入 optimistic Message；顺序完整读取 Runs、再读取正序 Messages，严格检查 run/session/input IDs 后才写回缓存与投影。 |
| 对账失败 | 通过：保留 accepted intent 和恢复按钮；显示安全错误，不把本地 query 画成已保存 Turn。 |
| cursor / 一致性 | 通过：受理对账不使用并行 Runs / Messages 请求，避免 accepted Run 已出现而 Message 尚未被同一快照读取的竞争。长期历史限制仍由 P2 正序 cursor 决定。 |
| SSE / 多 Run | 通过：实现扫描未包含 EventSource、`Last-Event-ID`、`/events`、`/stream` 或旧 hook；P3.6b.2 保持未开始。 |
| Mock / 后端 / report | 通过：未修改 Mock API、MSW 默认夹具、`backend/`、`report/`、真实 DB 或数据源。 |
| 自动验证 | 通过：`npm run typecheck`、`npm run test`（6 files / 40 tests）、`npm run build`、`npm run test:mock-api`（11 passed）通过。 |

## 已知风险与验收门槛

1. 当前独立 8100 Mock 不会把动态 accepted user Message 加进 `GET Session Messages`。因此其成功 POST 后会正确落入 “accepted but message not recovered” 提示，不能被用来宣称 P3.6b.1 成功对账已经浏览器验收。P3.6b.3 将单独补 Mock 合同。
2. 当前实现只允许每 Session 一个本地在途/未知/已受理意图；并行调查、多草稿和普通聊天仍是非目标。
3. sessionStorage 的 query 只用于当前 tab 的同 key 重试；后续若产品允许敏感命令或跨设备恢复，必须先做安全 / outbox 设计。
4. build 的 JS chunk `851.50 kB`（gzip `272.86 kB`）仍超过 Vite 500 kB 告警阈值；非阻塞，暂不在本切片处理。
5. P3.6b.2 的 Fetch SSE 可行性、浏览器 / 代理 Header 行为、Last-Event-ID 与多 Run cleanup 尚未验证，不能因 P3.6b.1 已通过就提前宣称断线恢复完成。

## 结论

P3.6b.1 实现审查与 active / archived / 网络未知 / 409 用户边界验收均通过，由本提交收口。提交后的下一步不是自动实现：需由用户确认 P3.6b.2（Fetch SSE 多 Run 恢复）和 P3.6b.3（Mock 合同）究竟先后及授权边界。
