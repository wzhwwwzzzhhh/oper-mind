---
name: dev-execute
description: Use when implementing a confirmed task card — developing in the worktree, running tests, one independent readonly review round, then commit + push + PR. Trigger on "开发", "实现", "写代码", "跑测试", "审查", "提交", "开 PR". Phase 3-5 of the lean dev loop, after dev-plan's task card is confirmed.
---

# 开发执行（OperMind 项目专属 · 轻量）

## 核心原则

任务卡是契约。先测试后实现，证据先于断言。**审查 1 轮，只 P0/P1 阻塞。** 交付即 PR，PR body 承载任务卡 + AC 证据。

## 前置

- 任务卡已被用户确认；开发在专用 worktree 内（见 `dev-plan` Phase 2）。
- 若 worktree 内开工前已有其他改动，先列隔离清单，逐文件核对，不整文件盲目暂存。

## Phase 3 开发

1. 每个切片先补/改测试（预期红）→ 实现（转绿）→ 小步重构。
2. 跨层数据走 Pydantic / TypedDict；Tool 继承 `Tool`；Connector 经显式 Application port / Executor 注入。
3. 每个新行为自问「对应任务卡哪条 AC」；映射不上就回 Phase 1 改卡，不加。
4. 禁止裸 `except`、新增生产 `print`；中文注释和用户可见日志；公开函数带类型标注。
5. 只读、最小权限、脱敏；凭据只走环境变量，不进日志 / 数据库普通字段 / Trace / 事件 / 结果 / 截图 / 响应。

## Phase 4 审查（1 轮）

派 readonly 子代理（explore 类型），输入：任务卡 + `git diff` + 相关测试文件。要求输出：

- 任务卡映射结论：漏项 / 越界 / 过度实现
- **P0**：安全红线（凭据泄露、未授权写、破坏性改动、mock 冒充真实）
- **P1**：功能错误 / 漏 AC / 契约破坏 / 越界文件
- **P2**：边界与降级缺失（**记录即可，不阻塞**）
- **不报 P3**（风格 / 命名 / 注释）
- **不报测试已覆盖的问题**——测试绿了就是证据
- 结论 PASS / FAIL（P0/P1 存在即 FAIL）

审查结论写在对话里，**不建 `review.md` 文件**。P0/P1 回 Phase 3 修；第 2 轮仍属同类 FAIL → 停下向用户说明，不无限修补。

## Phase 5 提交 + PR

1. `git fetch origin main && git merge origin/main`，本地解冲突，解完重跑相关测试。
2. 只暂存本任务文件；`git diff --cached` 核对只含本任务；`git diff --check` 干净。
3. 提交信息 `<类型>: <中文描述>`；一个切片一个提交；不直推 `main`。
4. push 分支，`gh pr create`。**PR body 必须包含**：
   - 任务卡全文（目标 / 只做 / 不做 / AC / 文件 / 风险回滚）
   - AC 证据表：每条 AC → 代码 / 接口 / 测试证据 → PASS/FAIL
   - 验证记录：相关 pytest、前端 `typecheck`+`test`+`build`（如适用）、`git diff --check`
   - 审查结论：1 轮结果 + P2 遗留清单
5. 把 PR 链接和一句话状态发给用户，等验收合并。

## 关键纪律

1. **证据先于断言**：没跑测试不说「做完了」。
2. **不越界**：只改任务卡列出的文件；要动别的，停下说明。
3. **不伪装**：mock 不当真实执行；未启用能力如实标明。
4. **安全默认**：只读、最小权限、脱敏、超时、参数校验。

## 常见错误

| 错误 | 修正 |
|---|---|
| 没跑测试就宣称完成 | 先跑，贴输出 |
| 用审查复核测试已覆盖的东西 | 审查只看测试看不到的：越界、漏 AC、契约破坏 |
| P2/P3 阻塞提交 | P2 记录；P3 不报 |
| 反复 FAIL 无限修补 | 第 2 轮同类失败停下交用户 |
| 提交前没合 main | 先 merge origin/main |
| `git add .` 全量暂存 | 只暂存任务文件 |
| PR 没写任务卡和 AC 证据 | PR body 即交付凭证 |

## 红灯（STOP）

- 无用户确认的任务卡
- 不在专用 worktree 开发
- 提交前未合 `origin/main`
- 凭据 / DSN / 原始 SQL / CoT 进日志、Trace、响应、截图或文档
- 未经确认新增公开接口、迁移、Connector、真实外部访问或高风险动作
- P0/P1 未修复或越界
- 相关测试未跑绿（或未如实标注未跑）

**发现任一红灯 ⇒ 停在当前切片，修复或取得用户确认前不提交。**
