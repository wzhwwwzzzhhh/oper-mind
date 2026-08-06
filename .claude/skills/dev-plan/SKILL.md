---
name: dev-plan
description: Use when starting development against a written OperMind PRD — setting up the workpack boundary, writing the implementation plan (docs/workpack/), and creating the feature branch. Trigger on "按PRD开发", "开发计划", "写开发文档", "切分支", "workpack", "开始干活", "规划工作包". It is Phase 0-2 of the dev workflow (plan → execute → deliver), called before dev-execute.
---

# 工作包计划（OperMind 项目专属）

## 核心原则
开发前先钉死「做什么 / 不做什么 / 怎么验证 / 改哪些文件」，把 PRD 切成 1–3 个独立可验收切片。
计划产出后**停审阅点**等用户确认，不直接动业务代码。

## 何时用 / 何时快速通道
**用**：接到 PRD 按下拉开发、要动正式产品代码（backend/src、frontend/src）、改动跨文件或多步时。
**快速通道**：≤1 文件、≤10 行净变更、无需搜索定位、不命中运行态/review/门禁/发布链路的小改，直接在对话里完成，跳过本 skill 的流程文档。
**不用**：写 PRD（那是 prd-writing）、审 PRD（prd-reviewing）、纯对话解答。

## 前置要求
- 必须先读：当前有效 PRD（`docs/prd/<域>/`）、`docs/prd/README.md`、`docs/产品定义.md`、`docs/路线图.md`、`docs/开发规范.md`。
- 若涉及安全边界（凭据/连接/权限/审批/写操作/破坏性改动），必须引用已确认 Design；没有先 STOP。

## 执行流程

### Phase 0 输入确认（必须）
1. 定位唯一当前 PRD：域、阶段、状态、范围。找不到匹配 PRD，或需求明显超出 PRD → 停在需求层，不写代码。
2. 输出「本工作包只做」和「明确不做」两张清单，逐项映射到 PRD 的功能需求或 AC 编号。
3. 检查工程闸门：新服务类型、Connector、真实连接、凭据、公开 API、数据库迁移、监控、权限、审批/执行能力、破坏性改动 → 必须已有 Design → Review → 用户确认；未确认就 STOP。

### Phase 1 写开发文档
目录：
```
docs/workpack/
  <阶段>-<切片 kebab>/        # 如 P4.2-db-agent-read-slice
    plan.md                   # 本切片的实现计划
    review.md                 # 子代理独立审查输出（dev-execute 回写）
    evidence.md               # AC 证据表（dev-execute 回写）
  README.md                   # 索引：活跃/已归档 工作包
```
`plan.md` 模板：
```markdown
# <阶段>-<切片> · 工作包计划

## 范围
### 只做
- <每项映射到 PRD 功能需求或 AC 编号，如 "AC1：<...>">

### 明确不做
- <防止越界的排除清单>

## 切片拆分（1–3 个独立可验收切片）
- [ ] S1: <可独立验收的最小切片>
- [ ] S2: ...

## 改动面（文件级）
- <拟新增/修改的文件，真实路径>
- <涉及迁移、接口契约、数据库变更时特别标注>

## 验证方法
- 后端：<backend/ 下真实测试命令>
- 前端：<frontend/ 下 typecheck/test/build，如适用>
- 门禁：git diff --check、相关 pytest 全绿

## 提交计划
- <按切片规划提交信息，<类型>: <中文描述>>
```

### Phase 2 切分支（worktree 化，多 Agent 并发的硬闸门）
- **这是进入 `dev-execute` 的硬闸门**：没有本工作包专用分支，不得开发、测试后提交或进入交付。
- **每个工作包在独立 worktree 里开发**，与主仓库工作区彻底隔离：
  - 开发基地目录：仓库外固定位置 `D:/market-handsome/oper-mind-worktrees/`（仓库外，git 不跟踪、不会污染仓库）。
  - 建 worktree 命令（在主仓库根执行）：`git worktree add "D:/market-handsome/oper-mind-worktrees/<切片>" -b <类型>/<切片> main`
  - 基线默认 `main`；用户明确指定其他基线时记录基线和理由。
  - 进入 worktree 开发：`cd "D:/market-handsome/oper-mind-worktrees/<切片>"`（后续命令都在 worktree 内执行）。
- **worktree 是全新 checkout**：仓库根的 `.venv`、`node_modules` 不会带过去，需在 worktree 内重建（后端 venv、前端 `npm install`）。
- 主仓库工作区可能被其他 Agent / PM 占用：**绝不在主仓库工作区直接开发**；只在那里管理分支、建 worktree、跑 PR 相关操作。
- 建 worktree 前先 `git worktree list`，确认该切片没有已存在的 worktree/分支，避免重复建。
- 若历史遗留的改动已在主仓库工作区且属于本工作包：在当前状态创建专用分支保留改动，再逐文件核对后**迁移进 worktree 或提交**；若混合了其他任务，必须建立「隔离提交清单」，逐文件或逐代码块核对，不得使用 `git add .`。
- 分支创建结果（worktree 路径 + 分支名 + 基线）必须写入 `plan.md`。

### Phase 3 停审阅点
- 将计划交用户确认：范围、切片、改动面、验证方法。
- **用户确认后才进入 `dev-execute`。** 未经确认不写业务代码。
- 若 Phase 2 未完成，必须停在这里；"当前分支看起来能用"不等于专用 worktree 已建立。

## 关键纪律
1. 计划是执行契约：切片、改动面、验证方法必须落在 `plan.md`，不留高档模糊项。
2. 不写实现细节到 PRD；实现方式写在 plan.md，由 execute 执行。
3. 边界 > 功能：「明确不做」与「只做」同样重要。
4. 工程闸门未过即 STOP，不要把"先跑起来"当通过理由。
5. 不阻塞式改动：不修改工作包外的文件。

## 常见错误
| 常见错误 | 修正 |
|---|---|
| 没有唯一 PRD 就写代码 | 先定位 PRD，找不到即 STOP |
| 计划没停审阅点直接开发 | Phase 3 必须等用户确认 |
| 切片过大无法独立验收 | 切成 1–3 个独立可验收切片 |
| 改动面含糊（"相关文件"） | 写真实文件路径与改动类型 |
| 闸门项未确认就推进 | 回 Phase 0 要求 Design→Review→用户确认 |
| 未创建专用分支就开发 | 先建立工作包分支，并把分支名写入 plan.md |
| 在主仓库工作区直接开发 | 用 `git worktree add` 到开发基地，隔离开发；主工作区只做管理 |
| 重复建同一切片的 worktree | 建前先 `git worktree list` 确认无已存在 worktree/分支 |
| 混合工作区未经核对就提交 | 建立隔离清单，逐文件/逐代码块审阅 staged diff |

## 红灯（STOP）
- 找不到匹配 PRD 或需求明显超范围
- 涉及新服务/Connector/凭据/迁移/权限/写操作等却无已确认 Design
- 计划缺少「明确不做」清单
- 改动面覆盖工作包外文件
- 切片无独立验证方法
- 未创建本工作包专用分支，或混合工作区没有隔离清单

**发现任一红灯 ⇒ 停下，不与用户确认人为放行。**
