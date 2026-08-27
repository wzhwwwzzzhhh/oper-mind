# P8-controlled-action-closeout · AC 证据表

> 工作包：P8-controlled-action-closeout（issue #100：受控动作与审批闭环——真实链路复核与 UI 反馈）
> PRD/Design 复用：`docs/prd/approval/P5-controlled-action-real.md`、`docs/design/approval/P5受控动作联合索引Design.md`
> 关联清单：`docs/完善清单.md` P0-1、P1-11；`docs/跑通验证.md` C1
> 交付：PR #107 已于 2026-08-27 squash 合并至 main

## S1 · P1-11 前端 UI 反馈（已交付 ✅）

| 需求 | 实现/测试证据 | 结果 |
|---|---|---|
| 批准/执行按钮 loading | 批准按钮 `loading={approve_mutation.isPending}`、执行按钮 `loading={execute_mutation.isPending}`（+ Modal `confirmLoading`）；测试 `批准/执行提交期间按钮进入 loading（请求未决）`、`执行期间二次确认按钮进入 loading（请求未决）` | PASS |
| 失败态"重新发起调查"入口（failed/blocked/expired/rejected） | `retryable()` + `rerun_mutation`：调用既有 `api_v1_client.rerun_run(source_run_id, {idempotency_key: randomUUID()})`；目标取 `source_run_id ?? run_id`；成功/失败如实反馈；rejected 无失败消息时中性说明；缺失来源 Run 诚实警告 | PASS |
| 字段缺失降级渲染 | `read_proposal` 仅强制核心字段（id/status），mode 与详情字段缺失时按可用字段降级渲染 + 诚实占位；测试 `字段缺失时按可用字段降级渲染，不整卡消失` | PASS |
| 安全：不展示 SQL/凭据/request id；不引入新 API | 面板只渲染脱敏摘要与静态文案；S1 无后端/公开 API 改动 | PASS |

- 面板聚焦：`npm run test -- --run src/features/workbench/action-proposal-panel.test.tsx` → **9 passed**。
- 合并最新 main 后前端全量：`npm run typecheck` 通过；`npm run test` → **210 passed / 20 files**；`npm run build` 成功。
- 独立审查：`docs/workpack/P8-controlled-action-closeout/review.md` → **PASS**（首轮 P1 已修复并复核闭环）。

## S2 · P0-1 受控动作闭环真实链路复核（已完成 ✅）

> 2026-08-27 在用户逐步确认授权、提案批准和执行确认后完成。目标严格限制为受控靶场
> `localhost:5433` 的 `postgres-target`，没有连接生产/预发布；DSN、凭据、原始 SQL、原始异常和内部请求 ID
> 均未写入证据。成功创建的索引按既定边界保留，未自动删除。

| 阶段 | 脱敏事实 | 结果 |
|---|---|---|
| 写前边界 | PostgreSQL、本地主机、固定端口 5433、固定服务 `postgres-target`、固定对象 `public.orders(customer_id, created_at)` | PASS |
| Preflight | 表与两列存在；同名有效/无效索引均不存在；执行计划为 Seq Scan | PASS |
| 诊断与提案 | Run `succeeded`；固定提案为 `pending_approval`；action/target/risk/verification plan 与白名单完全匹配 | PASS |
| 人工审批 | `local_operator` 明确批准；审批 action digest 与提案一致 | PASS |
| 二次确认与执行 | 用户独立确认执行后才发送执行请求；execution mode=`target`、status=`succeeded` | PASS |
| 独立 Verify | proposal=`verified`；index_exists/index_valid/plan_uses_index 均为 true | PASS |
| Postflight | 固定索引存在且有效；Seq Scan=false；Index Scan=true；命中目标索引=true | PASS |
| 审计事件 | proposal_created → approval_recorded → execution_requested → execution_started → precondition_checked → execution_completed → verification_started → verification_completed；各一次、序号连续 | PASS |

### 复核器与运行时缺陷修复

- 新增一次性复核器 `backend/scripts/verify_p8_s2.py`：DSN 仅从进程环境读取；写前严格校验边界；批准与执行分别使用新鲜 challenge；写后异常保守标记；输出只有脱敏结构化事实。
- 新增 `backend/tests/test_verify_p8_s2.py`，覆盖边界拒绝、人工 challenge、防重入、审计事件完整性，以及写前/写后失败语义。
- 真实链首次运行暴露 `RootCauseResource` 拒绝领域 `missing_index` 信号、导致结果响应 500；补充受控 `MissingIndexResource` 与序列化测试，并同步生成 `frontend/src/api/v1/generated.ts`。没有新增 endpoint 或数据库迁移。
- LLM provider 使用确定性 mock；PostgreSQL collector、固定 DDL executor、独立 Verify、FastAPI、临时应用持久化、人工审批和审计链路均为真实路径。

## 验证命令（S1 实测）

```
cd frontend
npm run typecheck        # 通过
npm run test -- --run src/features/workbench/action-proposal-panel.test.tsx   # 9 passed
npm run test             # 210 passed / 20 files（合并最新 main 后）
npm run build            # 成功
```

## 最终本地门禁

```text
ruff check                         # PASS
mypy src                           # 112 source files，PASS
pytest tests -q（清除目标 DSN）     # 630 passed
npm run typecheck                  # PASS
npm run test                       # 210 passed / 20 files
npm run build                      # PASS
git diff --check                   # PASS
```
