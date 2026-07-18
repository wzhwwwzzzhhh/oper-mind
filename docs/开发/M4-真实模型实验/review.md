# M4 Step 2 Review — Judge 关键点 ID 口径

> 审查日期：2026-07-18
> 审查快照：工作区未提交；覆盖 `step2-评分口径校准与关键点ID判定.md`。

## 结论

真实 Judge 的关键点评分已从原文逐字匹配改为 golden 编号选择，解决了语义/措辞不同导致
`key_points_recall` 被错误置零的问题。下游 `CaseResult` 与 `cases.jsonl` 仍保留原始关键点文本，
不需要迁移历史评测结构。

## 实现核对

- `src/eval/judge.py`
  - prompt 为每个 golden 关键点提供 `KP1...KPN`；
  - 仅接收 `key_point_ids`，过滤非法值并按首次出现顺序去重；
  - 映射回 `key_points_hit` 原文，保持既有 Runner / Schema 接口；
  - 根因分数安全转换并裁剪到 `[0.0, 1.0]`；
  - mock stub 未改变。
- `tests/test_judge.py`
  - 覆盖 ID 映射、非法/重复 ID、非列表 ID、JSON 失败和越界/非数值分数；
  - mock 路径测试继续保留。

## 验收证据

```text
.\.venv\Scripts\python.exe -m pytest tests\test_judge.py -q
11 passed in 0.98s
```

真实 `db-001` smoke：`root_cause_score=1.0`、`key_points_recall=1.0`，命中全部三条
黄金关键点，无运行错误。

## 剩余门槛

正式运行 65 条真实主实验前，仍需完成 Step 2 文档定义的 12 条人工抽检：DB / Server / Log /
Compound 各 3 条，人工与 Judge 命中集合至少 10 条完全一致。未达标时先修订 Judge prompt 或
数据集 golden，再重新抽检。

# M4 Step 3 Review — 实验条件切换与可比指标

> 审查日期：2026-07-18
> 审查快照：工作区未提交；覆盖 `step3-实验条件切换与可比指标.md`。

## 结论

M4 的 6 组实验条件已从 `--arm` 目录标签变为实际编排控制。单 Agent 基线、Debate / Reflection
消融和固定路由组都可在同一数据集、模型、裁判、工具、种子与关闭长期记忆的条件下比较。

## 实现核对

- `src/core/experiment.py`：集中定义 6 组不可变 ExperimentCondition，并拒绝非法 arm。
- `src/core/graph.py`：single_agent 覆盖策略为 direct 且保留主要领域 target；固定路由覆盖 strategy；
  no_debate 跳过 Debate；no_reflection 从 report 直达结束。
- `src/eval/metrics.py`：保留 pipeline_complete，新增按组解释的 condition_complete。
- `src/eval/runner.py`：记录从 Coordinator 诊断开始到 Judge 评分完成的 latency_ms。
- `src/eval/result_schema.py`：逐例、全局与 domain/difficulty 切片均加入完成率与平均延迟。
- `scripts/run_eval.py`：--arm 限制 6 组，--replicate 限制 1/2/3，并将两者纳入 config_hash 和 meta。

## 验收证据

- 全量测试：`55 passed in 10.55s`。
- 既有 direct / chain / parallel / debate 冒烟通过。
- single_agent 与 no_reflection 的 65 条 mock 产物已验证 arm、replicate、condition_complete、
  pipeline_complete 和 latency_ms。
- 5 个关键实验组的真实 smoke 已完成；具体 trace、质量和延迟记录在 Step 3 Test Evidence。

## 剩余门槛

1. Step 2 规定的 12 条人工抽检尚未执行；在其达到至少 10/12 命中集合完全一致之前，不启动正式
   6 × 3 × 65 的真实主实验。
2. 真实 full 组和 force_parallel 的 Debate 是否触发取决于具体用例中的实质冲突；正式实验需按
   trace 统计触发率，不得假设每个 parallel 样例都会进入 Debate。
3. 正式实验前需将每个 arm 的 replicate 1/2/3 运行命令、产物目录和失败重跑规则整理为实验执行清单。
