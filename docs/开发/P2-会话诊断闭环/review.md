# P2 独立审查 — 会话诊断闭环

> 更新时间：2026-07-26　|　结论：P2.1 已提交

## 审查范围

审查 P2.1 的领域关系、第一份业务 migration、Run 状态机、幂等受理、事件/SSE 顺序、结构化结果、安全数据边界、旧接口兼容与切片范围。未审查不存在的 ORM/HTTP 实现，因为本 Step 没有新增实现。

| 检查项 | 结论 | 设计结论 |
|---|---|---|
| 关系与外键 | 通过 | 用户 Message 在受理事务先创建，Run 指向 input_message；助手 Message 在成功后以可空 run_id 关联，避免 Message/Run 双向循环外键 |
| 首个 migration 范围 | 通过 | 仅 `sessions`、`messages`、`diagnosis_runs`、`run_events`、`diagnosis_results`、`run_idempotency_keys`；P4/P5 资源不提前入库 |
| 状态机 | 通过 | queued/running/terminal 转移受条件更新保护；终态不可逆；取消仅保留契约位置，不在本 Step 伪造执行接口 |
| 幂等 | 通过 | `(session_id, endpoint, idempotency_key)` 唯一；规范化 query 指纹区分重放与 `IDEMPOTENCY_KEY_REUSED` |
| sequence 与 SSE | 通过 | `next_event_sequence` 与 `UNIQUE(run_id, sequence)` 共同保护；SSE 只读已提交 RunEvent，sequence 十进制映射 `id` |
| 结构化结果与安全 | 通过 | DiagnosisResult/Evidence 在写入前与读取后 Pydantic 校验；禁止将原始日志、SQL、连接信息和工具原始返回塞进 JSON |
| 现有 Trace 映射 | 通过 | Coordinator Trace 映射为 P0.3 同名事件；Agent Core 不写数据库、不持有事务 |
| 旧接口兼容 | 通过 | P2 只新增 `/api/v1`；`/diagnose`、`/diagnose/stream` 保持即时且非持久化 |
| 范围控制 | 通过 | 没有新增依赖、表、迁移、Repository、Application Service、HTTP/SSE 代码、`frontend/` 或 `report/` 改动 |

## 已知风险与 P2.2 门槛

- SQLite 无法替代真实 PostgreSQL 的并发和锁语义；P2.2 必须先在 SQLite fresh DB 覆盖约束/迁移，P2.3 的并发事件追加再增加 PostgreSQL 集成门。
- `DiagnosisResult` 的真实结构化抽取尚未实现。P2.3 必须提供 ResultAssembler 端口和确定性 mock，不得解析 Markdown 伪造高置信结论。
- Event cursor 的不透明签名与过期策略属于 P2.4：先固定编码/验证，不提前声称 `EVENT_CURSOR_EXPIRED` 已实现。
- 长时间 Agent 调用不能放在数据库事务中；P2.3 的 worker 适配必须在受理提交后执行。

## 结论

P2.1 设计达到 P2.2 可实施标准并完成独立提交。提交信息：`docs: 完成P2会话诊断闭环设计`。提交后唯一下一步为 **P2.2：领域模型、首个业务迁移与 Repository**。
