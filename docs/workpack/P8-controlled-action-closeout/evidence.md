# P8-controlled-action-closeout · AC 证据表

> 工作包：P8-controlled-action-closeout（issue #100：受控动作与审批闭环——真实链路复核与 UI 反馈）
> PRD/Design 复用：`docs/prd/approval/P5-controlled-action-real.md`、`docs/design/approval/P5受控动作联合索引Design.md`
> 关联清单：`docs/完善清单.md` P0-1、P1-11；`docs/跑通验证.md` C1
> 分支：`feat/p8-controlled-action-closeout`（基线 main @ d299661，已合并 origin/main）

## S1 · P1-11 前端 UI 反馈（已交付 ✅）

| 需求 | 实现/测试证据 | 结果 |
|---|---|---|
| 批准/执行按钮 loading | 批准按钮 `loading={approve_mutation.isPending}`、执行按钮 `loading={execute_mutation.isPending}`（+ Modal `confirmLoading`）；测试 `批准/执行提交期间按钮进入 loading（请求未决）`、`执行期间二次确认按钮进入 loading（请求未决）` | PASS |
| 失败态"重新发起调查"入口（failed/blocked/expired/rejected） | `retryable()` + `rerun_mutation`：调用既有 `api_v1_client.rerun_run(source_run_id, {idempotency_key: randomUUID()})`；目标取 `source_run_id ?? run_id`；成功/失败如实反馈；rejected 无失败消息时中性说明；缺失来源 Run 诚实警告 | PASS |
| 字段缺失降级渲染 | `read_proposal` 仅强制核心字段（id/status），mode 与详情字段缺失时按可用字段降级渲染 + 诚实占位；测试 `字段缺失时按可用字段降级渲染，不整卡消失` | PASS |
| 安全：不展示 SQL/凭据/request id；不引入新 API | 面板只渲染脱敏摘要与静态文案；无后端/公开 API 改动；`generated.ts` 未动 | PASS |

- 面板聚焦：`npm run test -- --run src/features/workbench/action-proposal-panel.test.tsx` → **9 passed**。
- 前端全量：`npm run typecheck` 通过；`npm run test` → **209 passed / 20 files**；`npm run build` 成功。
- 独立审查：`docs/workpack/P8-controlled-action-closeout/review.md` → **PASS**（首轮 P1 已修复并复核闭环）。

## S2 · P0-1 受控动作闭环真实链路复核（⏳ 待真实资源授权与 DSN 注入）

> 前置（未满足即不能执行）：
> - **授权**：连接真实受控靶场（演示库，隧道 `127.0.0.1:5432`）并执行固定建索引动作，需用户明确授权（issue 闸门：真实资源测试须先确认授权、边界与脱敏）；
> - **DSN**：`OPERMIND_SERVICE_POSTGRES_TARGET_DSN` 需指向隧道演示库（凭据只从环境变量注入，不落库/不提交——当前 worktree 与 shell 均未配置）；
> - 受控靶场 `public.orders(customer_id, created_at)` 需存在且缺 `idx_orders_customer_created_at`。
>
> 复核步骤（授权与 DSN 就绪后执行）：
> 1. 后端以 `target` 模式启动（`OPERMIND_SERVICE_POSTGRES_TARGET_DSN` 注入，`alembic upgrade head`）；
> 2. 建会话绑定 `postgres-target` → 发慢查询诊断（含"慢查询/seq scan + 排查/分析"意图词）→ Run 成功；
> 3. `GET /api/v1/runs/{id}/action-proposal` → 断言 `pending_approval`（缺索引信号触发）；
> 4. 审批（approve + 幂等键）→ 二次确认执行（executions）→ 轮询至 `verified`；
> 5. 断言 Verify facts：`index_exists/index_valid/plan_uses_index` 均为 true（EXPLAIN 转 Index Scan）；
> 6. 证据落本表：API 快照 + 事件时间线 +（可选）截图；随后回写 `完善清单.md` P0-1 → ✅、`跑通验证.md` C1 → 已解决。

## 验证命令（S1 实测）

```
cd frontend
npm run typecheck        # 通过
npm run test -- --run src/features/workbench/action-proposal-panel.test.tsx   # 9 passed
npm run test             # 209 passed / 20 files
npm run build            # 成功
```