---
name: dev-execute
description: Use when implementing a confirmed task card — developing in the worktree, running the local gates (typecheck / test / build / lint), committing and opening a PR. Trigger on "开发", "实现", "写代码", "跑测试", "提交", "开 PR". Phase 3-5 of the lean dev loop, after dev-plan's task card is confirmed.
---

# 开发执行（OperMind 项目专属 · 轻量）

## 核心原则

任务卡是契约。先测试后实现，证据先于断言。**本地门禁全绿即交付**；子代理审查按风险分级，默认不做。交付即 PR，PR body 承载任务卡 + AC 证据。

## 前置

- 任务卡已被用户确认；开发在专用 worktree 内（见 `dev-plan` Phase 2）。
- 若 worktree 内开工前已有其他改动，先列隔离清单，逐文件核对，不整文件盲目暂存。

## Phase 3 开发

1. 每个切片先补/改测试（预期红）→ 实现（转绿）→ 小步重构。
2. 跨层数据走 Pydantic / TypedDict；Tool 继承 `Tool`；Connector 经显式 Application port / Executor 注入。
3. 每个新行为自问「对应任务卡哪条 AC」；映射不上就回 Phase 1 改卡，不加。
4. 禁止裸 `except`、新增生产 `print`；中文注释和用户可见日志；公开函数带类型标注。
5. 只读、最小权限、脱敏；凭据只走环境变量，不进日志 / 数据库普通字段 / Trace / 事件 / 结果 / 截图 / 响应。

## Phase 4 门禁（必须全绿，不可跳过）

**这是唯一的硬关卡。** 缺一项就是没做完。

| 改动面 | 必跑命令 |
|---|---|
| 后端 | `pytest tests -q`（至少相关测试文件）+ `ruff check .` + `mypy` |
| 前端 | `npm run typecheck` + `npm run test` + `npm run build` |
| 通用 | `git diff --check` 干净；敏感字面量扫描无命中 |

**为什么要 lint**：V2-2 WP1 曾漏掉一个 import，本地 pytest 全绿（`from __future__ import annotations` 让注解不解析），但 CI 的 `ruff` 报 `F821` 直接红。编译器/静态检查能查的，必须由门禁查，不能指望人工审查。

门禁不过不许提交；如实标注未跑的项，不得宣称完成。

## Phase 4b 子代理审查（按风险分级，默认不做）

| 改动类型 | 判定 | 子代理审查 |
|---|---|---|
| **普通** | 单层、不碰闸门项、<300 行净变更 | **不做** |
| **跨层** | 碰 `core/`、契约定义、跨 3 层以上、>300 行 | 1 轮 |
| **闸门** | 新 Connector / 真实连接 / DB 迁移 / 公开 API / 审批执行能力 | 1 轮 + 用户确认 |

判定原则：**先问「本地门禁能不能查出来」**。能查出来的（类型错、未定义名、测试覆盖的行为）交给门禁；只有门禁查不出来的（越界、漏 AC、契约破坏、安全语义）才值得派审查。

派审查时：
- readonly 子代理，输入任务卡 + `git diff` + 相关测试文件
- 只报 P0（安全红线）/ P1（功能错误 / 漏 AC / 契约破坏 / 越界文件）/ P2（边界与降级缺失，记录即可）
- **不报 P3**（风格、命名、注释、措辞）
- **不报测试已覆盖的问题**
- 结论写在对话里，不建文件

**审查报告的 P2 必须自己验证再采纳。** 误报的代价是写死代码 + 写无法失败的测试。核验方式：临时移除防护代码，跑测试看是否变红；不变红说明这条 P2 不成立或不可达。

P0/P1 → 回 Phase 3 修。第 2 轮仍同类 FAIL → 停下向用户说明。

## Phase 5 提交 + PR

1. `git fetch origin main && git merge origin/main`，本地解冲突，解完重跑门禁。
2. 只暂存本任务文件；`git diff --cached` 核对只含本任务；`git diff --check` 干净。
3. 提交信息 `<类型>: <中文描述>`；一个切片一个提交；不直推 `main`。
4. push 分支，`gh pr create`。**PR body 必须包含**：
   - 任务卡全文（目标 / 只做 / 不做 / 风险回滚）
   - AC 证据表：每条 AC → 证据 → PASS/FAIL
   - 验证记录：门禁命令与结果
   - 审查结论（仅跨层/闸门改动需要）+ P2 遗留清单（含核验结果）
5. 把 PR 链接和一句话状态发给用户，等验收合并。

## 关键纪律

1. **证据先于断言**：没跑门禁不说「做完了」。
2. **不越界**：只改任务卡列出的文件；要动别的，停下说明。
3. **不伪装**：mock 不当真实执行；未启用能力如实标明。
4. **安全默认**：只读、最小权限、脱敏、超时、参数校验。
5. **不为误报写代码**：P2 先核验可达性，不可达就不写防护。

## 常见错误

| 错误 | 修正 |
|---|---|
| 没跑门禁就宣称完成 | 先跑，贴输出 |
| **跳过 lint 只跑测试** | lint 是门禁的一部分，CI 会因为 lint 红 |
| **普通改动也派审查** | 按 Phase 4b 表判定；默认不做 |
| 用审查复核测试已覆盖的东西 | 审查只看门禁看不到的 |
| **照单全收审查的 P2** | 先核验；不可达的不写防护代码 |
| P3 阻塞提交 | 不报 P3 |
| 反复 FAIL 无限修补 | 第 2 轮同类失败停下交用户 |
| 提交前没合 main | 先 merge origin/main |
| `git add .` 全量暂存 | 只暂存任务文件 |
| PR 没写任务卡和 AC 证据 | PR body 即交付凭证 |

## 红灯（STOP）

- 无用户确认的任务卡
- 不在专用 worktree 开发
- 门禁未全绿（含 lint）却宣称完成
- 提交前未合 `origin/main`
- 凭据 / DSN / 原始 SQL / CoT 进日志、Trace、响应、截图或文档
- 未经确认新增公开接口、迁移、Connector、真实外部访问或高风险动作
- P0/P1 未修复或越界

**发现任一红灯 ⇒ 停在当前切片，修复或取得用户确认前不提交。**
