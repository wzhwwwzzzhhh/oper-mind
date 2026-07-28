# P3 独立审查 — 主前端工作台

> 日期：2026-07-28　|　结论：✅ P3.3b 持久化事件与 SSE 恢复通过独立 Review，等待提交授权
>
> 审查基线：`181e601 docs: 校正P3.3a提交状态并进入P3.3b`　|　工作分支：`feat/p3-workbench`

## 1. 审查范围

本次审查 P3.3b 的前端实现：RunEvent cursor 读取、事件最小运行时解析、REST/SSE 合并、原生 EventSource 生命周期、断线 REST 重同步和终态重读。未修改 P2 后端协议、旧接口、`report/`、真实数据库/8000，也未进入 P3.3c 独立 Mock FastAPI 验收或 P3.4 结构化结果。

## 2. 审查依据

- 合同与恢复语义：`docs/开发/P0-V1产品化基线/api-v1-contract.md:426-503`；
- P2 路由/SSE：`backend/src/api/v1/routes.py:360-429`、`backend/src/api/v1/sse.py:20-65`；
- P3.3 设计与 Step：`docs/开发/P3-主前端工作台/design.md`、`step3-run受理幂等与sse恢复.md`；
- 实现与测试：`frontend/src/api/v1/client.ts`、`queries.ts`、`frontend/src/features/workbench/run-events.ts`、`use-run-event-stream.ts`、`WorkbenchPage.tsx`、对应 Vitest/MSW files。

## 3. 独立审查结果

| 检查项 | 结论 | 审查结果 |
|---|---|---|
| RunEvent REST 契约 | 通过 | 仅调用 `GET /api/v1/runs/{run_id}/events`，cursor 原样回传，Query key 绑定 run；保持 `X-Request-Id` 和安全关联诊断 |
| 事件事实与解析 | 通过 | 只接受当前 Run、正整数 sequence、合同枚举事件类型、UTC `Z` 时间与对象 data；畸形/跨 Run/未知事件被忽略，未猜测 Trace 字段 |
| 合并与排序 | 通过 | REST 与 SSE 以 `(run_id, sequence)` 合并，保留首次合法事件、严格按 sequence 升序；测试覆盖重复 sequence 与非法输入 |
| EventSource 协议 | 通过 | 仅 queued/running Run 打开 `/api/v1/runs/{run_id}/stream`；初连 URL 不带 `after_sequence`，不设置 headers/Last-Event-ID，不读取 SSE response headers，避免 P2 双游标冲突 |
| 断线与终态 | 通过 | `onerror` 显示恢复状态并 REST 重读 Run/Event，不写成 Run failed、不创建第二条流；终态事件关闭 source、变为 idle，并重读 Run/Event/Session Runs/Messages |
| 刷新与生命周期 | 通过 | 既有 Session → Runs → Message → Run 后增加 Events；切换 Run、卸载、终态均关闭旧连接；终态 Run 不维持 SSE |
| P3.3c/P3.4/P4–P6 边界 | 通过 | 没有独立 Mock FastAPI、真实后端、结果卡、Trace 跳转、环境/数据源/告警/审批/知识假功能 |
| 测试与构建 | 通过 | `npm run typecheck` 通过；`npm run test` 为 3 files / 22 passed；`npm run build` 通过，仅有非阻断 chunk 大小提示 |

## 4. 审查发现与处理

- P3.2 既有深链测试原先只期望 4 个读取请求；P3.3b 合同正确新增 `/events` 后，该断言失败。已更新为 5 个按序请求，确认不是额外副作用。
- 初次 production build 暴露 `Number.isSafeInteger(sequence)` 不会将 OpenAPI `unknown` 缩窄为 `number`；已加显式 `typeof sequence === 'number'`，重新执行完整质量门通过。
- 普通 `git diff --name-only` 不显示未跟踪的新增事件合并器、EventSource hook 和 test helper；Review 已使用 `git status --short` 及文件清单核对，它们均属于 P3.3b 待提交范围。

## 5. 已知风险与非目标

1. 原生 EventSource 初连从最早可用事件重放，长历史可能增加客户端去重工作；这是 P2 当前双游标协议下正确性优先的选择，性能优化须先做独立协议设计。
2. EventSource 自动重连实际由浏览器实现；当前测试验证 URL、去重、error 重同步、不双开与终态关闭，不模拟浏览器私有 Last-Event-ID 细节。
3. P2 SSE 是已提交事件的轮询重放，不是生产级消息总线；慢客户端、保留策略、高吞吐、崩溃接管和认证授权仍属于 P7。
4. 真实数据库/8000 后端验收仍以后续 C1–C8 为门槛；本次 MSW 通过不能替代真实接入成功。

## 6. 结论与下一步

P3.3b 在既定范围内通过独立 Review。前端准确消费 P2 持久化 RunEvent/SSE 契约，断线和终态不会伪造成诊断失败，也没有引入旧 API、真实资产或后续阶段能力。

**当前状态：等待用户明确提交授权。提交后唯一下一步为 P3.3c：Mock FastAPI SSE 契约验收。**
