# Step 4 — 人工抽检校准

> 日期：2026-07-18
> 快照：工作区未提交；执行 Step 2 定义的 12 条人工与 LLM-as-Judge 一致性校准。

## Design

抽检样本固定为 DB / Server / Log / Compound 各 3 条，并在每个领域覆盖 easy、medium、hard。
为避免真实 API 调用中断导致整批成果丢失，使用 `scripts/generate_human_calibration.py` 逐条落盘：
每完成一条即写入记录、Judge 内部对照文件和不含 Judge 命中结果的盲审表。重复执行会跳过已完成
样本，从下一个样本续跑。

生成时每条样本均新建关闭长期记忆的 full 条件系统；同时 Runner 会在每条用例前清空短期会话，保证
报告不受相邻抽检样本影响。

## Step

1. 运行脚本生成或续跑 `experiments/m4-human-calibration/`。
2. 用户只填写 `blind_review.md` 的“人工命中 ID”和备注，不查看 `judge_reference.json`。
3. 用户填写完毕后，读取盲审表并与内部 Judge 对照文件比对，统计完全一致数和不一致原因。
4. 12 条中至少 10 条命中集合完全一致，才允许启动 6 × 3 × 65 条真实主实验。

## Code

- `scripts/generate_human_calibration.py`：抽检样本选择、逐条真实运行、断点续跑、盲审表和内部对照产物。
- `src/core/agent.py`、`src/core/coordinator.py`、`src/eval/runner.py`：评测短期会话隔离。

## Test

- 脚本先进行 Python 语法编译检查。
- 生成目录每完成一条至少有一个 `records/NN-case_id.json`；中断后重跑应跳过已完成样本。
- 完整生成后应有 12 条记录、盲审表、Judge 对照和 manifest。

## Review

- `experiments/` 被 Git 忽略，盲审表与 Judge 对照均不会提交。
- 人工标注必须由项目作者独立完成，避免由生成者替代人工校准。
