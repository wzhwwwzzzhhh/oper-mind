# M5 设计 — 多 Agent 价值对比

> 里程碑：M5　|　分支：待建（勿在 feat/m2-harness 上叠）
> 创建日期：2026-07-20
> 状态：🟡 计划（A-Plan 首个里程碑，承重墙）

## 1. 目标

拿到一条**可信的「多 Agent（full）vs 单模型（single_agent）」对比曲线**，量化多 Agent 协作相对单模型基线的收益边界。这是 A-Plan 最大风险点，须最早验证：一旦结论是「没全面赢」，尽早把 pitch 改成「量化了它在哪类场景有用」。

承接 M4——M4 已建 `single_agent`/`full` 等 6 组条件切换（`src/core/experiment.py`）与可比指标，本里程碑负责「补齐有意义的数据集 + 实际跑批 + 出数」。

## 2. 关键决策

- **基线公平性**：对比用**同模型、同工具、同种子**的 Python 单 Agent（`single_agent` arm），**绝不跨语言比 Java 版**（混淆变量）。
- **数据集去同质化**：当前 mock 世界只有一起故障（orders 索引级联），导致答案恒定、无区分度。M5 造多故障世界 + 区分度用例，让单模型「猜不到」。
- **指标口径**：修掉 stub judge 的假信号（见 step1）；主看根因命中率 / 关键点召回，辅以 token、延迟。
- **规模**：精简区分度集即可（够跑出可信数字），非论文规模。

## 3. Step 分解

| Step | 内容 | 主要改动文件 |
|---|---|---|
| step1 | 评测口径修复（recall=0.015 假信号） | `src/eval/judge.py`（+ 测试、重跑） |
| step2 | 多故障 mock 世界（3–4 起可切换） | `data/mock_db.py`/`mock_logs.py`/`mock_server.py`、新增 `data/scenarios.py` |
| step3 | 区分度用例集（表象误导 + 真分歧） | `data/eval/cases.jsonl`、按需 `data/eval/schema.py`/`validate.py` |
| step4 | 对比实验与指标（single vs full + token/延迟） | `src/core/llm.py`、`src/eval/metrics.py`、`scripts/run_eval.py`、`experiments/` |

## 4. 验收

- stub judge 不再产出误导性 recall；真实裁判 recall 可解释。
- 存在 ≥3 起互不相同的可切换故障场景，区分度用例含「表象误导」与「真分歧」两类。
- 产出 single_agent vs full 的对比结果（落盘 `experiments/<hash>/`），并能按场景/难度分层解读。
- `scripts/smoke_pipeline.py` 回归通过。
