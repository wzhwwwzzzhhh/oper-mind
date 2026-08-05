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
- CI / 相关测试已过，`git diff --check` 干净。
- 没有 P0/P1 未决，没有越界文件，没有未确认的闸门项。

## 执行流程

### Phase 6 push → PR → 合并
1. `git push -u origin <分支>`。
2. 用 `gh` 建 PR，基准 `main`，标题 = 中文提交主题，body 含：范围、AC 映射、review 结论、验证证据（测试命令与结果）、相关 PRD/Design 路径。
3. 等待 GitHub CI / checks；不过则修复（回 `dev-execute`）或说明，不强行合并。
4. 通过后合并（偏好 squash merge，保留干净历史），随后本地 `git checkout main && git pull` 拉回。
5. 记录 PR URL 交用户。

### Phase 7 收尾归档
1. 更新 `docs/prd/README.md` 当前进展：阶段状态 → 完成（或迁移到对应域 README）。
2. 归档工作包：`git mv docs/workpack/<阶段>-<切片>/ docs/workpack/归档/<阶段>-<切片>/`（保留 plan/review/evidence，只读不删）。
3. 若存在明确后续事项，在工作包移交记录中写明（回到 roadmap / dev-plan）。
4. 更新 `docs/workpack/README.md` 索引。

## 产物
- PR（含 URL）、合并提交、本地 main 已拉回
- `docs/prd/README.md` 状态更新
- `docs/workpack/归档/` 下已归档的工作包

## 关键纪律
1. **未 PASS 不交付**：review 非 PASS、测试未全绿，不得 push / 建 PR / 合并。
2. **不直推 main**：所有改动进 main 必经 PR + CI。
3. **只交付工作包**：PR 里只有本工作包文件；发现范围外提交先停下说明。
4. **CI 是硬闸**：CI 失败 = 修复而非绕过。
5. **收尾留痕**：PRD 状态与工作包归档必须更新，不留"做完了但没归档"。

## 常见错误
| 错误 | 修正 |
|---|---|
| review 未 PASS 就建 PR | 回 dev-execute 修复再审 |
| CI 红就合 | 修复到绿后再合 |
| 忘了更新 docs/prd/README.md | 收尾必须推进 PRD 状态 |
| 工作包不归档 | 移到 docs/workpack/归档/ |
| PR 混入范围外文件 | 检查 PR diff 只含工作包文件 |

## 红灯（STOP）
- review ≠ PASS 或 evidence 不完整
- CI 未通过
- PR diff 含工作包外文件
- 未经确认的闸门项（未建 PR 就动 main、绕过 CI 合并、强推）

**发现任一红灯 ⇒ 停止交付，回到交付链条前一步。**