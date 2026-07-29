# R1 / P3.5–P3.6a 个人会话主体验 — 独立审查

> 审查日期：2026-07-29　|　结论：✅ P3.6a 实现审查与用户人工验收均通过，准予提交。

## 审查范围

- P3.5 的个人长期会话主线是否被 P3.6a 正确落实；
- P2 Session、Message、Run、Result 契约是否仅以既有 GET 方式准确消费；
- 刷新、cursor、空/归档/读取错误、关联错误和 Result 错误是否诚实；
- P3.6a 与 P3.6b/P4/P5/P6、`report/`、真实资源的边界是否保持；
- 测试、构建、文档、计划、AGENTS/CLAUDE 和隔离文件是否一致。

## 独立核对结果

| 审查项 | 结论 |
|---|---|
| 用户主线 | 通过：默认视觉顺序是 user Message → 调查摘要 → 已保存 assistant Message，而非 Run 列表/选中 Run 工作台。 |
| P2 GET 契约 | 通过：只读取 `GET Session`、`GET Session Runs`、`GET Session Messages`；组件测试核验读取顺序。 |
| POST / SSE | 通过：P3.6a 没有发送控件、`POST`、`Idempotency-Key`、EventSource、`Last-Event-ID` 或事件面板；这些保留给 P3.6b。 |
| 关联真实性 | 通过：以 `input_message_id` 和 assistant `run_id` 做关联；重复、缺失、跨 Session/字段问题显示协议异常，不自行选择。 |
| 成功与 Result | 通过：只有已持久化 assistant Message 才显示答复；成功缺答复显示 `ANSWER_RECOVERY_PENDING`；Result 非法仍保留真实答复并标记 `RESULT_PROTOCOL_ERROR`。 |
| 失败/取消/未终态 | 通过：只显示真实调查状态，不伪造答复或实时进度。 |
| cursor / 长期历史 | 通过：保留 P2 正序 cursor，并提供 Runs/Message 的继续加载；明确未实现最近优先、向前加载的新 API 语义。 |
| 空、归档与读取错误 | 通过：空会话、归档只读、API 错误与安全 request/trace 诊断均有明确状态。 |
| 旧深链 | 通过：旧 Run 深链仍可进入对应 Session，但不额外读取单 Run，不把 Run 恢复成主对象。 |
| P4/P5/P6 与 `report/` | 通过：没有监控、数据源、告警、Action、Approval、Incident、多人协作或假数据；`report/` 无改动且仍是研发边界。 |
| 真实资源与后端 | 通过：未改 `/api/v1`、Application Service、Repository、ORM、Alembic、旧 `/diagnose*`，未连接真实 8000/DB/数据源。 |
| 自动验证 | 通过：`npm run typecheck`、`npm run test`（5 files / 33 tests）、`npm run build` 均通过。 |
| 隔离与文档 | 通过：未读取/修改/暂存隔离文件；仅当前 P3.6a 前端与治理文档在提交候选范围。 |

## 发现与风险

1. 用户已使用独立 8100 Mock 和未处于 Windows TCP 排除范围 `5141–5240` 的 Vite 端口完成浏览器人工验收；未以真实 8000 替代验收后端。
2. 构建输出单个 JS chunk 为 `843.21 kB`（gzip `270.26 kB`），Vite 发出超过 500 kB 的非阻塞警告；性能拆包不应夹带到 P3.6a，应另开切片。
3. 现有 P3.4c Mock 主要覆盖 Run/Result/SSE 技术状态；P3.6a 没有修改其夹具，以免把 UI 改造和 Mock 语义改造混入同一提交。人工验收应关注真实关联异常提示不被误称为完整产品历史。
4. P3.6a 仍不是普通聊天：P2 没有普通 message send 契约，P3.6b 也只能发送调查型问题，且必须使用稳定幂等键与刷新/SSE 恢复。

## 结论

P3.6a 代码、文档审查与用户可视化验收均通过，现按逐文件暂存规则提交。提交后的唯一下一步是 P3.6b 的 Design，不得直接实现发送、SSE、监控、告警或处理。
