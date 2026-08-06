---
name: dev-deliver
description: Use when delivering a completed, reviewed workpack — pushing the feature branch, creating a pull request against main, waiting for CI, merging, pulling main back, and closing out the workpack. Trigger on "提交交付", "建PR", "push", "合并", "收尾", "归档工作包", "PR审核通过后合并". It is the final phase of the dev workflow, called after dev-execute produced green commits and a PASS review.
---

# 工作包交付（OperMind 项目专属）

## 核心原则
交付是收尾闭环：只有"审查 PASS + 测试全绿 + 无未决阻塞项"的工作包才允许 push / 建 PR / 合并。
不直推 `main`；合并走 PR + CI；收尾要更新产品文档状态并归档工作包。

## 前置要求（任一不满足即 STOP）
- `docs/workpack/<阶段>-<切片>/` 存在，`plan.md` 用户已确认，`review.md` = PASS，`evidence.md` AC 证据表完整。
- 本地分支 = `<类型>/<切片>`，提交信息符合 `<类型>: <中文描述>`。
- `git remote get-url origin` 成功，且已确认远端存在 PR 基线分支（默认 `main`）；没有 remote 不得进入 push 阶段。
- `git status --short` 中没有未审阅的暂存/工作区改动；若存在其他工作包改动，必须有隔离清单，且 PR diff 只能包含本工作包提交。
- 用 `git diff origin/main...HEAD --name-only` 核对提交范围；用 `git log origin/main..HEAD --oneline` 核对提交数量和提交信息。
- CI / 相关测试已过，`git diff --check` 干净。
- 没有 P0/P1 未决，没有越界文件，没有未确认的闸门项。

## 执行流程

### Phase 6 push → PR → 合并
1. `git remote get-url origin`、`gh auth status`、`gh repo view` 预检全部通过；任一失败即 STOP。
2. **合前拉 main（关键）**：push 前先 `git fetch origin main && git merge origin/main`（或 rebase），
   在本地解掉冲突并重跑相关测试；确保 PR 不会"合后又矛盾"。若 main 有新提交而本地未合入，不得 push。
3. `git push -u origin <分支>`，不得 force push。
4. 用 `gh pr create --base main` 建 PR；body 必须含范围、AC 映射、review 结论、验证证据、相关 PRD/Design 路径和未执行项。
5. 用 `gh pr view <number> --json baseRefName,headRefName,files,statusCheckRollup` 核对 base、head 和文件范围；不符合即 STOP。
6. 等待 GitHub CI / checks；不过则修复（回 `dev-execute`）或说明，不强行合并。
7. 只有用户明确要求合并且 checks 全绿后，才执行 squash merge；不得自动批准自己的 PR 或绕过 required review。
8. 记录 PR URL、CI 结果、合并 commit；随后执行 `git switch main`、`git pull --ff-only origin main`。

### Phase 7 收尾归档
1. **收尾文档不能直接改本地 `main`**：`docs/prd/README.md`、PRD 文件 frontmatter、`docs/workpack/README.md` 和归档移动必须在功能分支上完成，并纳入同一个 PR；合并后发现遗漏必须另开 follow-up 分支/PR。
2. 更新 `docs/prd/README.md` 当前进展：阶段状态 → 完成（或迁移到对应域 README）。
3. **同步更新 PRD 文件 frontmatter**：把本工作包对应的 PRD 文件顶部 `status: 已确认` 改为 `status: 完成`，`updated` 改为合并日期。**必须与第 2 步的 README 双写一致**——两处都要是「完成」，不得只改一处。
4. 归档工作包：`git mv docs/workpack/<阶段>-<切片>/ docs/workpack/归档/<阶段>-<切片>/`（保留 plan/review/evidence，只读不删）。
5. 若存在明确后续事项，在工作包移交记录中写明（回到 roadmap / dev-plan）。
6. 更新 `docs/workpack/README.md` 索引，并在 PR diff 中复核收尾文件仍属于本工作包。
7. **清理 worktree（PR 合并后必须）**：`git worktree remove "D:/market-handsome/oper-mind-worktrees/<切片>"` + `git branch -d <类型>/<切片>`，
   再 `git worktree prune`；避免 worktree 越积越多、占用磁盘和污染 `git worktree list`。

## 产物
- PR（含 URL）、合并提交、本地 main 已拉回
- `docs/prd/README.md` 状态更新
- PRD 文件 frontmatter `status: 完成` 已双写更新
- `docs/workpack/归档/` 下已归档的工作包

## 关键纪律
1. **未 PASS 不交付**：review 非 PASS、测试未全绿，不得 push / 建 PR / 合并。
2. **不直推 main**：所有改动进 main 必经 PR + CI。
3. **只交付工作包**：PR 里只有本工作包文件；发现范围外提交先停下说明。
4. **CI 是硬闸**：CI 失败 = 修复而非绕过。
5. **收尾留痕**：PRD 状态（README + frontmatter **双写一致**）与工作包归档必须更新，不留"做完了但没归档"。

## 常见错误
| 错误 | 修正 |
|---|---|
| review 未 PASS 就建 PR | 回 dev-execute 修复再审 |
| CI 红就合 | 修复到绿后再合 |
| 忘了更新 docs/prd/README.md | 收尾必须推进 PRD 状态 |
| 只改 README 没改 PRD frontmatter | frontmatter `status: 完成` 与 README 必须双写一致，一处完成两处都是完成 |
| 工作包不归档 | 移到 docs/workpack/归档/ |
| PR 混入范围外文件 | 检查 PR diff 只含工作包文件 |
| 合并后直接在 main 补文档 | 回到功能分支，另开 follow-up PR |
| push 前没合 main | 先 `git fetch origin main && git merge origin/main` 本地解冲突 |
| 合完不删 worktree/分支 | `git worktree remove <切片>` + `git branch -d <分支>` + `git worktree prune` |

## 红灯（STOP）
- review ≠ PASS 或 evidence 不完整
- CI 未通过
- PR diff 含工作包外文件
- remote、base、head 或 PR 文件范围未核对
- 合并后需要直接写 main 的收尾改动
- PRD 收尾只改 README 未改 frontmatter，或两处状态不一致（一处完成一处已确认）
- 未经确认的闸门项（未建 PR 就动 main、绕过 CI 合并、强推）
- push 前未把 origin/main 合入本分支解冲突
- PR 合并后未清理 worktree / 分支（`git worktree list` 仍有残留）

**发现任一红灯 ⇒ 停止交付，回到交付链条前一步。**
