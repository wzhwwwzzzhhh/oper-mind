# M5 Step4 — 对比实验与指标

> 状态：✅ 代码完成并通过 code-review + mock 验证；**真实跑批待用户执行**（花钱、外部调用，不擅自跑）。
> 分支：`feat/m5-agent-comparison`

## 目标

产出「多 Agent（full）vs 单模型（single_agent）」对比曲线 + token/延迟成本，量化多 Agent 的收益边界。

## 决策（已确认）

- **对比矩阵**：头牌 `single_agent` vs `full`；消融 `no_debate` / `no_reflection`（分两阶段控成本）。
- **token/延迟核算**：延迟已有；新增诊断模型 token 累计。
- **切片**：按 `scenario`（S1–S4）与 `case_group`（mislead / conflict / legacy_compound / single_domain）——多 Agent 价值主要看 mislead/conflict 两组，避免被 45 条 single_domain 稀释。
- **裁判独立性**：诊断 `agnes-2.5-flash`（弱）、裁判 `deepseek-v4-flash`（强），跨厂不同模型，缓解自偏好偏差。

## Code 改动

- `src/core/llm.py`：`LLMClient.total_tokens` 累计真实 `response.usage.total_tokens`（mock 恒 0）。
- `src/eval/runner.py`：`run_case` 在 route 后、judge 前快照 `coordinator.llm.total_tokens` 取差 → 本例诊断 token（裁判用独立实例，不计入）。
- `src/eval/result_schema.py`：`_case_group` 归类；CaseResult 加 tokens/scenario/case_group；EvalSummary 加 mean_tokens + by_scenario + by_case_group。
- `scripts/run_eval.py`：打印 mean_tokens。
- `scripts/compare_arms.py`（新）：读多个 `experiments/<hash>/` → arm 对比表 + 按 case_group 的根因命中矩阵。

## Test / mock 验证

```text
python -m pytest -q                                    → 72 passed（+4：_case_group/token/切片）
OPERMIND_API_KEY=mock python scripts/run_eval.py --arm single_agent   → 77 例、mean_tokens=0、切片落盘
  （by_case_group=conflict/legacy_compound/mislead/single_domain，by_scenario=S1..S4）
python scripts/compare_arms.py <h1> <h2>               → 对比表 + 分组矩阵正常
```
mock 下 stub 判分是噪声，仅验管路；质量信号需真实 LLM。

## 真实跑批命令（交用户执行）

```bash
# Phase A —— 头牌对比（调用真实 LLM，产生费用）
python scripts/run_eval.py --arm single_agent --real --seed 42
python scripts/run_eval.py --arm full         --real --seed 42
python scripts/compare_arms.py <single_agent的config_hash> <full的config_hash>

# Phase B（可选，消融，有预算再跑）
python scripts/run_eval.py --arm no_debate     --real --seed 42
python scripts/run_eval.py --arm no_reflection --real --seed 42
```

## 已知限制

- 真实跑批费用/耗时随 arm×77 例×多轮 ReAct 增长；Phase A 先行。
- 每场景仅 4 条区分度用例，够出信号、非论文级统计规模。
- 若 full 未全面胜过 single_agent：按 case_group 解读「在 mislead/conflict 上有收益、single_domain 上单模型够用」，结论仍可辩护。
