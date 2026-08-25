# P8-controlled-action-closeout · 独立审查

## 结论

PASS

S1（前端 ActionProposalPanel UI 反馈）经独立只读子代理审查，首轮发现 1 项 P1（rejected 终态无"重新发起调查"入口，入口被嵌套在 `failure &&` 内而 rejected 无 failure_message），修复后复核 PASS；修复未引入新的 P0/P1。

## 首轮问题与修复

- [P1] rejected 提案取不到"重新发起调查"入口（入口依赖 `failure_message`，而 rejected 在后端不置 failure_message）→ 修复：入口按 `show_rerun_entrance = !read_only && retryable(status) && Boolean(rerun_target)` 独立渲染，与失败 Alert 解耦；rejected 且无 failure_message 时渲染中性说明"提案已被拒绝；可重新发起调查以生成新提案"，不伪造失败文案。
- [P2] `source_run_id`/`run_id` 均缺失时入口静默隐藏 → 修复：渲染诚实警告"缺少来源 Run"，并补交互测试。
- [P3] execute 按钮 loading 未单测、rerun 测试未证明 source_run_id 优先级 → 补 execute loading 测试；rerun 测试改用相异 source_run_id 断言优先取值；mode 缺失时 tag 颜色改为 gold（不近似 target 蓝色）。

## AC 证据表（S1）

| 需求 | 代码/测试证据 | 结果 |
|---|---|---|
| 批准/执行按钮 loading | `ActionProposalPanel.tsx` 批准/执行按钮 `loading={…isPending}` + Modal `confirmLoading`；测试 `批准/执行提交期间按钮进入 loading`、`执行期间二次确认按钮进入 loading` | PASS |
| 失败态"重新发起调查"入口（failed/blocked/expired/rejected） | `retryable()` + `rerun_mutation` 独立于 failure 渲染；复用既有 `api_v1_client.rerun_run(source_run_id, {idempotency_key: randomUUID()})`；测试覆盖四态（含 rejected 中性说明） | PASS |
| 字段缺失降级渲染 | `read_proposal` 仅强制 id/status，其余按可用字段降级 + 诚实占位（模式未返回/标题/描述/边界/风险/验证计划）；测试逐项断言 | PASS |
| rerun 复用安全（幂等键、目标来源、会话失效） | 每次点击新幂等键；`source_run_id ?? run_id`；`session_id` 前缀失效 session-runs/session-messages | PASS |
| 安全红线（不泄露/不伪造/无公开 API/不改后端） | 新增渲染全为静态文案或如实反馈；无 SQL/凭据/request id；无后端与公开 API 改动 | PASS |

## 验证记录

- 前端全量：`npm run typecheck` 通过；`npm run test` → 203 passed / 20 files；`npm run build` 成功。
- 面板聚焦：`npm run test -- --run src/features/workbench/action-proposal-panel.test.tsx` → 9 passed。

## 非阻塞后续

- S2（P0-1 真实链路复核）需真实受控靶场授权与 `OPERMIND_SERVICE_POSTGRES_TARGET_DSN` 注入，审查时尚未执行；执行后需按 `docs/跑通验证.md` C1 回写。