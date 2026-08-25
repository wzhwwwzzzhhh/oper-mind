# P8-controlled-action-closeout · 工作包计划

> issue：#100（受控动作与审批闭环——真实链路复核与 UI 反馈）
> 复用已确认 PRD：`docs/prd/approval/P5-controlled-action-real.md`（完成状态）
> 复用已确认 Design：`docs/design/approval/P5受控动作联合索引Design.md`（已确认）
> 关联清单：`docs/完善清单.md` P0-1（① ② 已合入 main，③ 真实复核未做）、P1-11（未修）
> 关联卡点：`docs/跑通验证.md` C1（代码已修、端到端未复验）
> 基线：main（2eb058c，2026-08-25 已合入 origin/main d299661）；worktree：`D:/market-handsome/oper-mind-worktrees/p8-controlled-action-closeout`；分支：`feat/p8-controlled-action-closeout`；PR：#107
> 计划状态：2026-08-25 用户确认（"继续"），S1 已交付、S2 待真实资源授权与 DSN 注入

## 范围

### 只做
- **S1（P1-11，前端 UI 反馈，轻流程）**——只改 `frontend/src/features/workbench/ActionProposalPanel.tsx` 与其测试：
  - 批准 / 执行按钮 loading：`approve_mutation.isPending` / `execute_mutation.isPending` 时按钮 loading，与既有拒绝按钮一致；
  - 失败态重试 / 重新发起调查入口：proposal 处于终态失败（blocked / failed / expired / rejected）时，提供"重新发起调查"入口，调用既有 `api_v1_client.rerun_run(source_run_id)`（复用 P8 已交付的 rerun API；每次点击新幂等键，目标取 `source_run_id ?? run_id`），成功/失败如实反馈；
  - 字段缺失降级渲染：`read_proposal` 从"全字段必填否则整卡消失"改为"仅核心字段（id/status）必填，mode 与详情字段（标题/描述/固定边界/风险/验证计划）缺失时按可用字段降级渲染并展示诚实占位（如'模式未返回'）"，不伪造内容；
  - 补前端交互测试（loading、失败重试调用、降级渲染）。
- **S2（P0-1 ③，受控动作闭环真实链路复核）**——真实靶场端到端复核，产出证据并回写文档：
  - 隧道 + 受控靶场（演示库）授权后：诊断 Run（绑定 `postgres-target`，触发缺索引信号）→ 生成提案 → 人工审批 → 二次确认执行（真实 `CREATE INDEX CONCURRENTLY`）→ 独立 Verify（EXPLAIN 确认 Index Scan）→ `verified`；
  - 记录证据（API 快照、事件时间线、可选截图）写入 `evidence.md`；
  - 回写 `docs/完善清单.md`（P0-1 → ✅ 注明日期与验证方式，P1-11 → ✅）、`docs/跑通验证.md`（C1 → 已解决）。

### 明确不做
- 不连接真实生产 / 预发布库；执行器只接受 `postgres-target`（P5 已确认边界不变）。
- 不新增公开 API、不新增数据库迁移、不新增 Connector；`generated.ts` 无需重新生成。
- 不改 mock 数据源（`data/mock_db.py`、`data/scenarios.py`）与 S1–S4 评测路径。
- 不做自动批准 / 自动执行 / 自动回滚；不做 RBAC / 多用户审批。
- 不处理 `docs/跑通验证.md` C2（demo schema.sql 与固定对象对齐，记为后续待办，非本 issue 范围）。
- 不触碰主仓库工作区其他未提交改动（agent-runtime 文档），只在本 worktree 内开发。

## 切片拆分
- [ ] S1：ActionProposalPanel loading / 失败重试入口 / 降级渲染 + 前端交互测试
- [ ] S2：真实靶场全链路复核（需用户授权）+ 证据落盘 + 清单 / 跑通验证回写

## 改动面（文件级）
- `frontend/src/features/workbench/ActionProposalPanel.tsx`（修改：loading、重试入口、降级渲染）
- `frontend/src/features/workbench/action-proposal-panel.test.tsx`（修改：补测试）
- `docs/workpack/P8-controlled-action-closeout/plan.md`（新建，本文件）
- `docs/workpack/P8-controlled-action-closeout/evidence.md`（新建，S2 证据）
- `docs/workpack/P8-controlled-action-closeout/review.md`（新建，独立审查结论）
- `docs/workpack/README.md`（修改：登记/归档）
- `docs/完善清单.md`（修改：P0-1、P1-11 状态回写）
- `docs/跑通验证.md`（修改：C1 状态回写）
- 仅 S2 需要：`config/config.local.yaml`（git-ignore，仅本机放真实 LLM 配置，不提交）与后端启动环境变量

## 验证方法
- 前端：`npm run typecheck`、`npm run test -- --run src/features/workbench/action-proposal-panel.test.tsx`、`npm run build`（在 `frontend/`）。
- 后端（S2 前置回归）：`..\.venv\Scripts\python.exe -m pytest tests/test_p5_controlled_action.py tests/test_action_proposal_list.py -q`（在 `backend/`）。
- S2 真实复核（仅在用户授权后执行）：后端 `target` 模式（`OPERMIND_SERVICE_POSTGRES_TARGET_DSN` 指向隧道演示库）→ 建会话绑定 `postgres-target` → 发慢查询诊断（含"慢查询+排查/诊断"意图词）→ Run 成功 → 提案 `pending_approval` → 审批 → 执行 → 轮询至 `verified`（facts: `index_exists/index_valid/plan_uses_index`）→ EXPLAIN 转 Index Scan。
- 门禁：`git diff --check` 干净；只暂存本工作包文件；敏感值（DSN/凭据/SQL 原文）不进日志、文档、测试输出与 git。

## 提交计划
- S1（前端）：`feat: 提案审批面板 loading、失败重试入口与降级渲染（issue #100，完善清单 P1-11）`
- S2（复核 + 文档）：`docs: 受控动作闭环真实链路复核证据与清单状态回写（issue #100，P0-1）`
- 若 S2 复核发现真实链路缺陷：按缺陷修复提交，补充对应测试后再合入同一 PR。

## 工程闸门说明
- S1 属 §7.1 轻流程（修 bug / 接线已存在 rerun 能力 / UI 打磨），无新增能力承诺。
- S2 涉及**真实外部资源连接与真实执行**，按 `开发规范.md` §6 / §7 与 issue 闸门，**必须**先经用户确认：授权范围（仅隧道演示库 `postgres-target`）、边界（绝不连生产/预发布）与脱敏方式（DSN/凭据/SQL 原文不落任何产出）。