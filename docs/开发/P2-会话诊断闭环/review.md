# P2 独立审查 — 会话诊断闭环

> 更新时间：2026-07-26　|　结论：P2.3 已通过独立审查，待用户授权提交

## 已提交基线

- P2.1 设计：`8f27717 docs: 完成P2会话诊断闭环设计`。
- P2.2a schema：`11634b4 feat: 完成P2.2a领域模型与首个业务迁移`。
- P2.2b Repository：`5cf2c6b feat: 完成P2.2b Repository端口与SQLAlchemy实现`。

## P2.3 审查范围

审查 Application Service 短事务、Session/Run 受理与归档、幂等、条件状态更新、事件 sequence、成功/失败终态、Message/Run 跨表一致性、Coordinator/ResultAssembler 适配、安全 JSON 边界、Repository 事务纪律和旧接口范围。P2.4 HTTP/SSE 不在本 Step。

| 检查项 | 结论 | 审查结果 |
|---|---|---|
| 事务归属 | 通过 | 仅 `application/services.py` 的统一事务辅助函数调用 commit/rollback；Repository、Coordinator 适配和 Agent 不控制事务 |
| 受理原子性 | 通过 | 单短事务写 input Message、queued Run、幂等记录和 sequence=1 `run_queued`；显式 flush 保证无 ORM relationship 时的 Message→Run 外键写入顺序 |
| 幂等 | 通过 | 固定 endpoint + Session + key 作用域；规范 query SHA-256；同 key/同指纹回放、不同指纹抛应用冲突；非幂等完整性错误不被伪装为重放 |
| 状态与重复 worker | 通过 | queued→running 由条件更新认领并写 `run_started`；已 running/终态 Run 不重复执行；成功/失败仅从运行态收口 |
| sequence 与事件 | 通过 | Run `next_event_sequence` 通过原子 update returning 预留，逐事件短事务写入；最终仍由 `UNIQUE(run_id, sequence)` 保护 |
| 成功/失败原子性 | 通过 | 成功事务写 Result/助手 Message/succeeded/final event；组装失败会 rollback 成功写入后再安全失败；失败只写安全 code/message 与 `run_failed` |
| Message/Run 一致性 | 通过 | 执行前验证 input Message 存在、同 Session 且为 user；助手 Message 写入前验证 `run_id`/`session_id` 与 Run 一致，承担无物理 `messages.run_id` FK 的责任 |
| 执行隔离 | 通过 | `run_started` 提交后才调用 executor；测试以独立 Session 读取 running 状态确认执行器处于无事务区间 |
| Coordinator/JSON 安全 | 通过 | Adapter 仅传 type/node/time/有限 strategy，丢弃 detail、原始 Markdown 和 executor data；保守 assembler 不伪造 Evidence/根因 |
| 分层与越界 | 通过 | 新增 application/ 与 infrastructure/diagnosis/ 已同步规则；domain 无 SQLAlchemy 泄露；未新增 API/SSE/旧 API/前端/真实数据源改动 |
| 回归 | 通过 | P2 定向 32 passed；完整后端 119 passed；direct/chain/parallel/debate pipeline smoke 通过；1 条既有弃用警告 |

## 已知风险与 P2.4 门槛

- SQLite 测试不能替代 PostgreSQL 高并发的幂等唯一键竞争、`UPDATE ... RETURNING` 和 sequence 锁语义；P2.4/P7 必须增加受控 PostgreSQL 集成或等价并发门。
- P2.3 暂无 HTTP 层，`ApplicationError` 尚未映射 P0.3 错误体/状态码；P2.4 必须实现安全错误映射、请求/trace ID、Pydantic 资源模型和不透明 cursor。
- SSE 只能在 P2.4 重放已提交 RunEvent；不得在 executor 内直接推送或读取未提交数据。
- 结构化 Result JSON 的正式 Pydantic 资源级脱敏/校验必须在 P2.4 衔接，保守 assembler 不应被误作真实诊断事实。

## 外部未提交改动

工作区存在 `docs/00-项目方案说明书.md` 的外部 1 行文本改动；本 Step 未读取内容、未修改、未暂存，且必须排除在 P2.3 提交之外。另有两个包初始化文件显示为修改但内容 hash 与 HEAD 一致、无 diff，不纳入提交。

## 结论

P2.3 在既定边界内通过独立审查。待用户授权后可提交；提交后的唯一下一步为 **P2.4：`/api/v1` 与 SSE 恢复**。
