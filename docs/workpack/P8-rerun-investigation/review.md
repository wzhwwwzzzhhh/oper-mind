# P8-rerun-investigation · 独立代码审查

> 关联 PRD：`docs/prd/session/P8-rerun-investigation.md`（issue #65）
> 审查方式：readonly 子代理独立审查，审查者与开发视角分离。

## 第一轮审查（FAIL → 修复）

**总体：FAIL**（P1 文档交付缺失；代码本身幂等/终态/脱敏链路自洽，无越界文件，未发现功能错误、契约破坏或安全漏洞）。

| 级别 | 发现 | 处置 |
|---|---|---|
| P1 | `docs/接口清单.md` 未标「重跑」已交付、未补 `POST /runs/{id}/rerun` 行；`docs/路线图.md` 未登记工作包（plan「只做」明确要求） | 已补：接口清单缺表标 ✅ + 补行 + 汇总 21/43/41 + 交付说明块；路线图登记 issue #65 |
| P2 | 迁移 downgrade 防御未测（plan 声称「测试中覆盖」） | 新增 `test_rerun_迁移存在来源行时拒绝回滚` |
| P2 | `_load_rerun_idempotency_after_conflict` 竞争重读新路径未直接测 | 新增 `test_rerun_唯一键竞争后幂等重读` |
| P2 | `handlers.ts` 模块级可变 `rerun_state/rerun_messages` 跨用例串扰风险 | 移除可变状态，rerun handler 静态返回，动态行为由局部 `server.use` 覆盖 |
| P3 | 链式重跑展示指向最近一级、重跑 service 已移除时 409 | 设计接受（纯前端推导 / 诚实降级），不改 |

AC 证据表（第一轮）：AC1–AC10 全部 PASS（13 项测试 + 前端 133）。

## 复审（PASS）

**总体：PASS**。四项 P1/P2 修复逐一复核到位：接口清单计数 21/43/41 实测自洽（routes.py 43 条 v1 路由、会话工作台 21、未接线仅会话 PATCH/DELETE）；两个新测试真实构造场景并实测通过（test_run_rerun.py 13 passed）；handlers 无可变状态残留（grep 确认）；`git diff --check` 干净；改动文件均在本工作包范围。

> 小注（非本包引入，不构成阻塞）：接口清单「模型设置 已有（7）」表头与表内 8 行不一致为既有遗留。

## 结论

PASS。无 P0/P1。两轮审查后工作包可提交。
