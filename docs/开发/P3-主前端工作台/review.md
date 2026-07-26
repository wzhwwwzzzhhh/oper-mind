# P3 独立审查 — 主前端工作台 Design

> 日期：2026-07-26　|　结论：✅ 通过，待用户授权暂存/提交

## 审查依据

独立核对 `54f02e5`、`backend/src/api/v1/routes.py:146-429`、`backend/src/api/v1/schemas.py:63-318`、`docs/开发/P0-V1产品化基线/api-v1-contract.md:426-514`、P0 原型、P3 Design 与计划真相源。本轮未实现前端或后端代码。

| 检查项 | 结论 | 审查结果 |
|---|---|---|
| P2 API 契约 | 通过 | 仅消费 `/api/v1` Session/Message/Run/Result/Event/SSE；结果来自 `GET /runs/{run_id}` 公开资源，未假设不存在端点 |
| 刷新恢复 | 通过 | Session → Runs → Message → 选定 Run/Result/Event → 非终态 SSE；cursor 不解码且不跨 Session 复用 |
| 幂等/关联 ID | 通过 | Run 创建 UUID 幂等键、超时同 key 重试；消费 request/trace header 与 meta、UTC `Z`，不伪造业务状态 |
| SSE | 通过 | `Last-Event-ID` 自动恢复、主动重建 `after_sequence`、sequence 去重、终态关闭、错误读恢复；不使用旧即时 SSE |
| P3/P4/P5/P6 边界 | 通过 | 仅展示 P2 实体；未实现能力是诚实空状态，无假资源/可操作控件 |
| frontend/report 边界 | 通过 | frontend 被确认未初始化；P3.1 才建独立工程并保留原型。report 不嵌入、不改造、不复用，只提供可选无参数外部入口 |
| 旧 API/真实资产 | 通过 | 禁止旧 `/diagnose`、`/diagnose/stream`；不接入真实 DB/数据源/认证，不创建 SQLite |
| 分步和质量门 | 通过 | P3.1 仅初始化/外壳；后续读模型、Run/SSE、结果和联调独立；保留 build、测试、mock、pipeline 和人工验收 |
| 文档一致性 | 通过 | A/B Plan、AGENTS/CLAUDE、P2 历史 HANDOFF 回填 `54f02e5`；AGENTS/CLAUDE 必须 hash 一致；提交后唯一下一步为 P3.1 |

## 发现与处置

1. P2.5 已在 Git 提交 `54f02e5`，但恢复时多份文档仍写“待提交”；本轮只回填状态并将 P2 HANDOFF 转为历史完成快照。
2. EventSource 不能由应用任意设置自定义请求头；设计改为浏览器 `Last-Event-ID` 自动重连、主动重建用 `after_sequence`，不制造冲突游标。
3. 没有确认的 `report/` trace deep-link 契约；P3 不拼 `trace_id`，P6 如需深链另行设计。

## 已知风险

P2 cursor 尚未绑定 Session scope；前端通过 Session 绑定的 query/cursor 生命周期降低跳过结果风险，服务端授权/scope 后续收口。P2 BackgroundTasks、SSE 短轮询和 SQLite 并发不是生产加固；P3 只正确显示和恢复。具体 Node/包版本/MSW handler 在 P3.1/P3.2 确认，不能假装已安装验证。

## 结论

P3 Design 通过独立审查。本轮只完成文档和状态校正，**待用户授权提交后，唯一下一步为 P3.1：前端工程初始化与产品外壳。**