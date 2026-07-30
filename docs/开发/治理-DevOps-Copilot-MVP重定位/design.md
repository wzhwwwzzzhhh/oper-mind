# P4.0 Design — 受控订单慢 SQL 靶场与调查—修复—验证闭环

> 日期：2026-07-29，修订：2026-07-30　|　状态：**✅ Work 1 真实验收完成**
>
> 产品定位：`README.md`　|　稳定代码基线：`adfb8fb feat: 完成P3.6b.1发送意图与202对账`
>
> **安全前提：**靶场不是生产连接。用户明确授权创建专用数据库并只允许使用本地隧道固定目标；任何偏离目标、凭证缺失或边界不一致均必须 fail-closed。

## 1. 目标与验收故事

P4 只实现一个可重复、可演示、可验证的受控故障：**订单服务因 `orders(user_id, created_at)` 联合索引缺失而出现慢 SQL、日志超时与接口延迟。**

```text
用户：订单查询接口变慢，帮我排查。
→ Coordinator 选择 parallel，调度 DB / Log / Server Agent
→ 三个 Agent 从受控靶场读取真实只读证据
→ 系统给出“缺失联合索引”的结构化根因、证据、风险和固定修复提案
→ 用户点击批准
→ 受控执行器仅在靶场执行 create_orders_user_created_index
→ Verify 重新读取索引、执行计划、服务指标和日志窗口
→ 前端明确显示已验证成功、失败或无法验证，绝不伪造结果
```

Work 1 只负责这条闭环的靶场地基与可复核 smoke；不改 OperMind Agent、API、前端、迁移或产品执行器。

## 2. 已完成能力如何复用

| 资产 | 本 MVP 的用法 |
|---|---|
| LangGraph + Coordinator + DB/Log/Server Agent | 作为调查内核；P4.1 才补靶场适配和必要状态/提示词。 |
| Debate / Reflection / Report | 仅在提高首个场景可信度时启用，避免为了机制而增加链路。 |
| P2 Session / Run / Result / RunEvent | 可作为调查、审批和审计的持久化基础；新语义先设计，不绕过 Application Service。 |
| `/api/v1`、SSE 与 React Query | 可复用为产品状态和进度传输；不因复用而强制回到 P3.6 会话路线。 |
| `frontend/` | 后续改造成 DevOps Copilot 主流程；以调查与处置为中心。 |
| `report/`、M5 评测 | 保持研发、Trace、实验和毕业设计用途，不阻塞 MVP。 |

## 3. Work 1 靶场设计

### 3.1 固定目标与禁止目标

| 项目 | 值 |
|---|---|
| 连接地址 | `127.0.0.1:5433`（用户服务器的本地隧道） |
| 唯一数据库 | `opermind_demo` |
| 唯一 schema | `opermind_demo` |
| 唯一表 | `orders` |
| 唯一允许变更的索引 | `idx_orders_user_created (user_id, created_at)` |
| 本地订单服务 | `127.0.0.1:18080` |

用户于 2026-07-30 授权创建 `opermind_demo`，明确要求不碰其已有 `gongkar` 数据库。实现因此禁止将 `gongkar` 作为默认、回退或探测目标；不执行库列表、schema 列表或其他库查询。

### 3.2 数据与动作

- `start`：校验固定连接目标，创建 `opermind_demo` schema、`orders` 表、固定索引，使用 `COPY` 写入 300,000 条确定性 demo 数据，启动本地订单服务，采集正常基线；
- `probe`：只调用本地服务固定接口，聚合耗时和请求 ID；
- `inject`：只执行 `DROP INDEX opermind_demo.idx_orders_user_created`；
- `repair`：只执行同名、同定义的 `CREATE INDEX`；
- `verify`：同看索引存在性、`EXPLAIN (FORMAT JSON)` 计划、性能窗口与 JSONL 匹配日志；
- `clean`：停止脚本启动且实例 ID 匹配的本地服务，删除 `opermind_demo` schema 和靶场 `runtime/`。不删数据库。

所有 SQL 为脚本内固定语句；没有模型 SQL、用户 SQL、DDL/DML 参数入口或 `pg_sleep`。

### 3.3 证据判定

- 正常：索引存在，计划使用目标索引，当前窗口没有慢查询日志；
- 故障：索引不存在、计划存在 `Seq Scan`、P50 相对 baseline 至少 `1.25x` 且增加至少 `15 ms`，并有慢查询日志；
- 恢复：索引和索引计划恢复，P95 不高于 `1.8x` baseline，慢查询日志归零；
- 任一证据不满足则验证失败，不能仅凭“命令成功”报告修复成功。

隧道环境的小样本 P95 易受单次网络抖动放大，故故障延迟门使用 P50；P95 仍记录在报告中审计。阈值根据 2026-07-30 隧道真实测量校准；它们是靶场验收门，不是生产告警阈值。

## 4. Work 2+ 的接口设计预留

Work 1 的管理脚本不是产品适配器。P4.1 开始前必须独立设计：

1. 只读 PostgreSQL、服务指标、日志三个 adapter 的连接配置、超时、最小权限和确定性 mock；
2. 结构化 Evidence、RootCause、Proposal、VerificationResult 的 domain/application 边界；
3. Coordinator 如何同时保留 source failure、不确定性和可引用证据；
4. 固定 action ID 如何经过审批、审计、白名单执行和 Verify，而不是让 LLM 直接调脚本；
5. API/SSE 与 `frontend/` 怎样表达“未验证”“证据不足”“已验证恢复”。

## 5. 风险与结论

- 本地 `127.0.0.1` 只是隧道端点，不自动等于安全；安全来自用户授权、专用数据库、程序内硬校验和清理边界。
- PostgreSQL 真实执行时间会受隧道与服务器负载影响，故 smoke 以相对退化、计划和日志三类证据共同判定。
- Work 1 通过后只证明靶场闭环可信，不代表产品多 Agent 调查链路已经接入。

用户已先授权 Work 1；真实 smoke 通过后，下一步必须是收口 Review/Commit。P4.1 仍需新的 Design → Review → 用户授权。