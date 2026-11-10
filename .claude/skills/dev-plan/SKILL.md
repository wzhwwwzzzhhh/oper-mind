---
name: dev-plan
description: Use when starting development — writing a short task card in conversation (目标 / 只做 / 不做 / AC / 文件 / 风险), getting one user confirmation, and creating an isolated worktree branch. Trigger on "开发", "开始干活", "写开发计划", "切分支", "任务卡", "workpack". Phase 0-2 of the lean dev loop (task card → confirm → worktree), before dev-execute.
---

# 任务卡与开工（OperMind 项目专属 · 轻量）

## 核心原则

**一个任务卡 = 一个可交付切片**，≤20 行，写在对话里。用户确认一次，就开工。不写 `docs/workpack/plan.md`，不进 PRD 状态机，不双写索引。

**交付时任务卡进 PR body**（`dev-execute` 负责），这样以后还能从 PR 找回「当时答应做什么」。

## 任务卡模板（对话内输出，六项缺一不可）

```markdown
### 任务卡：<一句话标题>

**目标**：<做完能得到什么，用户能感知到什么>

**只做**：
- <每项对应 AC 或 PRD 需求>

**不做**：
- <防越界的排除清单>

**AC（可测）**：
1. <一条命令 / 一个接口响应 / 一个页面行为可验证>
2. ...

**改动文件**：
- <真实路径>

**风险与回滚**：
- <最可能坏的地方；怎么回滚>
```

## 例外：五类闸门改动

新 Connector / 真实连接 / DB 迁移 / 公开 API / 审批执行能力 → 先走 `arch-design` 的例外 Design（≤60 行）+ `arch-review` 1 轮 + 用户确认，再写任务卡。任务卡里加 5 行「决策 / 风险 / 回滚」摘要。

普通改动**不写 Design**。

## 一次只做一片

多切片任务（如一个阶段分 WP1/WP2/WP3）串行：

1. 一个任务卡只覆盖一片可独立交付的能力。
2. 下一片的任务卡，在上一片交付后才写——上一片跑通后，下一片的输入是事实而非推测。
3. 任务卡里写一句「下一片是什么」，但不展开。

## Phase 0 读输入

- 有 PRD 就读当前 PRD 的相关需求段；没有就以用户这次的需求为准（对话即需求）。
- 读 `docs/事实源/开发规范.md` 的相关约束；扫一眼要改的文件现状。
- 不做全仓库考古；只在需要定位时用搜索。

## Phase 1 确认（唯一关卡）

把任务卡发给用户，等「确认 / 改这里」。确认后直接进 Phase 2，不再单独确认计划。

## Phase 2 worktree

- 开发基地：`D:/market-handsome/oper-mind-worktrees/`（仓库外，git 不跟踪、不污染仓库）。
- 主仓库根执行：`git worktree add "D:/market-handsome/oper-mind-worktrees/<切片>" -b <类型>/<切片> main`
- 建前先 `git worktree list`，避免重复建。
- worktree 是全新 checkout：`.venv`、`node_modules` 不在，执行 `.claude/scripts/init-worktree.ps1`（Windows，用 pwsh）或 `.claude/scripts/init-worktree.sh`（Unix）重建。
- 已知坑：
  - `backend/requirements.txt` 保持纯 ASCII 注释（中文注释在 Windows GBK 下 `pip` 报 `UnicodeDecodeError`）。
  - `npm run generate:api` 需要 8000 端口有活后端；没有就先 `python -c "import json; from src.app import app; json.dump(app.openapi(), open('openapi.json','w'))"` 落盘，再 `npx openapi-typescript openapi.json -o src/api/v1/generated.ts`。
- **绝不在主仓库工作区开发**（主仓库只做管理、建 worktree、跑 PR 相关操作）。

## 关键纪律

1. 任务卡 ≤20 行；写不完说明切片太大，先拆。
2. 「不做」和「只做」同等重要。
3. 任务卡里没有的需要，不在开发中偷偷加——回 Phase 1 改卡。
4. 闸门项没确认即 STOP。

## 常见错误

| 错误 | 修正 |
|---|---|
| 任务卡写成 200 行设计文档 | 只写六项；细节留给代码 |
| 一个任务卡塞进多个独立能力 | 拆成多个串行任务卡 |
| 上一片没交付就规划下一片 | 等交付 |
| 闸门改动直接开写 | 先例外 Design → 1 轮审查 → 用户确认 |
| 在主仓库工作区直接开发 | 建 worktree |
| 计划没确认就动代码 | 等「确认」 |

## 红灯（STOP）

- 五类闸门改动没有例外 Design / 审查 / 用户确认
- 任务卡没有「不做」清单或 AC 不可测
- 在上一片未交付时提前做下一片
- 在共享主仓库工作区开发

**发现任一红灯 ⇒ 停下，不人为放行。**
