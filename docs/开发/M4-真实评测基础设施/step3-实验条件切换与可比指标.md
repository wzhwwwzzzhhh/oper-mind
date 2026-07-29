# Step 3 — 实验条件切换与可比指标

> 日期：2026-07-18
> 快照：工作区未提交；承接 Step 1 双模型配置与 Step 2 Judge 评分口径校准。

## Design

### 目标

将 `scripts/run_eval.py` 的 `--arm` 从实验目录标签升级为真实的编排条件开关，支持公平地比较
单 Agent、完整多 Agent、Debate / Reflection 消融和固定路由策略。每组按 `replicate=1/2/3` 跑同一份
65 条数据，产出可按 case_id 对齐的质量、完成率和端到端延迟数据。

### 实验组矩阵

| arm | 路由 / Agent | Debate | Reflection |
|---|---|---|---|
| `single_agent` | 自动判断主要领域 `db/server/log`，强制只执行该 Agent | 跳过 | 保留 |
| `full` | 自适应 `direct/chain/parallel` | 保留 | 保留 |
| `no_debate` | 自适应路由 | 跳过 | 保留 |
| `no_reflection` | 自适应路由 | 保留 | 跳过 |
| `force_chain` | 固定 Server → DB → Log | 跳过 | 保留 |
| `force_parallel` | 固定三 Agent 并行 | 实际结论冲突时触发 | 保留 |

全部实验组关闭长期记忆，以保证用例独立。记忆消融不纳入 M4 主实验；未来若研究记忆，只能为每个
用例注入独立、固定的记忆快照，禁止让不同评测用例共享可写长期记忆。

### 单 Agent 基线定义

路由器仍为每个问题生成主要领域 `target=db|server|log`。`single_agent` 忽略原始 strategy，强制
执行 direct 节点并调用该 target 对应 Agent。这样单 Agent 与 full 组保持同诊断模型、同路由能力、
同领域 Prompt 和同工具；唯一移除的变量是多 Agent 协作。

单 Agent 保留 Report 和 Reflection；Reflection 的独立贡献由 `no_reflection` 组衡量。

### 接口与数据契约

新增 `ExperimentCondition`（名称可在实现中按现有命名调整），由 arm 映射以下固定字段：

```text
routing_mode: adaptive | single_agent | force_chain | force_parallel
enable_debate: bool
enable_reflection: bool
```

- `build_system()`、`CoordinatorAgent`、`build_diagnosis_graph()` 接收实验条件。
- route 节点在自适应以外的条件下覆盖 strategy，但仍计算/保留 single_agent 的主要领域 target。
- `--arm` 仅允许上表 6 个值；新增 `--replicate`，仅允许 `1`、`2`、`3`。
- config_hash 与 meta.json 同时包含 arm、replicate、诊断模型、裁判模型、数据集、种子、是否 mock。

### 指标契约

逐例 `CaseResult` 和 `cases.jsonl` 新增：

```text
condition_complete: bool
latency_ms: float
```

- `latency_ms`：从开始调用 `coordinator.route(case.query)` 到独立 Judge 返回评分的总时长，包含路由、
  Agent、工具、Debate、Reflection 与 Judge。
- `pipeline_complete`：保持既有定义，仅表示 trace 同时包含 report 和 reflection，是完整链路工程指标。
- `condition_complete`：按实验条件解释完成：
  - `full`、`no_debate`、`force_chain`、`force_parallel`：trace 有 report + reflection；
  - `no_reflection`：trace 有 report；
  - `single_agent`：trace 有 direct + report + reflection。

批次 `EvalSummary`、`summary.json` 和按 domain / difficulty 切片新增：

```text
condition_complete_rate
mean_latency_ms
```

论文跨组主指标使用 root_cause_score、key_points_recall、condition_complete 和 latency_ms；
pipeline_complete 仅用于说明完整系统链路覆盖，不用于惩罚有意跳过 Reflection 的消融组。

## Step

1. 建立 arm → ExperimentCondition 的单一映射和参数校验，避免 CLI、bootstrap 与 graph 各自解释 arm。
2. 修改编排图条件边，使 6 组都只改变矩阵规定的变量。
3. 在 Runner 计时，将 condition_complete 与 latency_ms 写入逐例结果和批次汇总。
4. 将 arm、replicate、诊断模型、裁判模型纳入实验指纹和 meta。
5. 先跑 mock 单测与 pipeline 回归，再对每个机制至少跑 1 条真实 smoke。
6. 完成 12 条人工抽检后，再跑 6 组 × 3 次 × 65 条的正式真实主实验。

## Code

计划涉及：

- `src/core/`：实验条件对象、system 装配、Coordinator 和 LangGraph 条件接线。
- `scripts/run_eval.py`：arm / replicate 参数、实验条件装配、meta 和配置指纹。
- `src/eval/runner.py`、`src/eval/metrics.py`、`src/eval/result_schema.py`：端到端计时、
  condition_complete、逐例与汇总结果。
- `tests/`：实验条件、图 trace、CLI 参数、结果契约、延迟与汇总指标测试。
- `docs/开发/M4-真实评测基础设施/review.md`：实现后追加真实 smoke、人工抽检与正式实验前置检查。

不改变：

- `data/eval/cases.jsonl` 的 golden 内容；
- Step 2 的 key_point_ids 裁判契约；
- 所有评测组关闭长期记忆的 M3 约束。

## Test

### 单元与集成测试

1. 6 个 arm 都能映射为确定的 ExperimentCondition；非法 arm 或 replicate 不是 1/2/3 时 CLI 报参数错误。
2. `single_agent` 在原本 chain / parallel 问题中只出现 direct，一次且带主要领域 target。
3. `no_debate` 的并行冲突 trace 不出现 debate，仍出现 report + reflection。
4. `no_reflection` trace 不出现 reflection，且 `pipeline_complete=False`、`condition_complete=True`。
5. `force_chain` 只走 chain；`force_parallel` 只走 parallel，冲突时仍可触发 debate。
6. CaseResult 校验 `latency_ms >= 0`；summary 与 domain/difficulty 切片正确聚合完成率和平均延迟。
7. config_hash 在 arm、replicate 或裁判模型变化时不同。
8. 全量 `pytest tests -q` 和 `scripts/smoke_pipeline.py` 通过。

### 真实 smoke

使用已配置的真实诊断 / 裁判模型，分别运行至少一条：single_agent、no_debate、no_reflection、
force_chain、force_parallel；核对 trace、judge_is_stub=False、latency_ms 与 meta。真实 smoke 成功后，
先完成 Step 2 约定的 12 条人工抽检，再启动完整 6 × 3 × 65 主实验。

## Review

- 每次消融只变更实验组矩阵中的一个变量；模型、裁判模型、数据集、种子、工具和长期记忆策略固定。
- `full` 是主系统，`single_agent` 是公平主基线；no_debate / no_reflection 用于机制消融；force_chain /
  force_parallel 用于路由策略对比。
- 真实 API 调用失败、限流或 Judge 解析失败不得静默混入统计结论；正式实验必须记录失败 case，并在相同
  arm / replicate 下单独重跑后再生成论文汇总。

## Test Evidence

### 红灯

Step 3 初始测试运行时，`src.core.experiment` 尚不存在：

```text
ModuleNotFoundError: No module named 'src.core.experiment'
```

建立实验条件对象后，首次图条件测试仅 `no_reflection` 用例失败。原因是测试错误地断言自适应
`no_reflection` 必须走 direct；实际查询含“很慢”，关键词路由正确选择 chain。修正测试为只校验该
实验组的契约“存在 report、没有 reflection”后，6 组编排测试通过。

随后全量回归发现 `_config_hash()` 的指纹引用了 `replicate`，但函数签名漏传该参数，抛出：

```text
NameError: name 'replicate' is not defined
```

补充 replicate 参数与指纹测试后修复。

### 自动化验证

```text
.\.venv\Scripts\python.exe -m pytest tests -q
55 passed in 10.55s
```

```text
.\.venv\Scripts\python.exe scripts\smoke_pipeline.py
✅ 三条路径全部跑通,pipeline 已接通(route → agent → [debate] → report → reflection)
```

冒烟脚本运行后已恢复 `data/memory.json`，SHA-256 与运行前一致：
`FA502DECEBD6D0F9DEE3AF2DF95A8458B755D14146115E6EAC7B31E1A161A475`。

mock CLI 产物验证：

| arm | replicate | cases | pipeline_complete | condition_complete | mean_latency_ms |
|---|---:|---:|---:|---:|---:|
| single_agent | 1 | 65 | 1.0 | 1.0 | 4.33 |
| no_reflection | 2 | 65 | 0.0 | 1.0 | 5.42 |

非法 `--arm invalid-arm` 会被 argparse 在启动评测前拒绝；`meta.json` 已落盘 arm 与 replicate，
所有逐例结果都有非负 `latency_ms`。

### 真实 smoke

2026-07-18 使用 `deepseek-v4-flash` 作为诊断与裁判模型，5 个关键实验组均完成真实 smoke：

| arm | case_id | trace 核心节点 | condition_complete | pipeline_complete | latency_ms | root_cause_score |
|---|---|---|---:|---:|---:|---:|
| single_agent | db-001 | direct → report → reflection | true | true | 40783.9 | 1.0 |
| no_debate | parallel-001 | parallel → conflict_check → report → reflection | true | true | 85134.7 | 0.6 |
| no_reflection | db-001 | direct → report | true | false | 14823.4 | 1.0 |
| force_chain | db-001 | chain ×3 → report → reflection | true | true | 92488.0 | 1.0 |
| force_parallel | parallel-001 | parallel → conflict_check → report → reflection | true | true | 87190.6 | 0.6 |

五次均为 `judge_method=llm_judge` 且无运行 error。force_parallel 本轮没有触发 debate，因为冲突检测
认为三个领域结论互补、无实质冲突；这符合“仅冲突时进入 Debate”的实验契约，不视为失败。

### 评测短期会话隔离补充

在准备人工抽检时复查发现：M3 已关闭长期记忆，但 `run_suite()` 复用同一 Coordinator 时，领域 Agent 的
`ShortTermMemory` 会保留最近会话。这同样会使后续评测用例看到前序内容，违背“用例独立”约束。

修复方式：`BaseAgent.reset_for_evaluation()` 清空短期会话与思考记录；`CoordinatorAgent`
聚合该操作；`run_suite()` 在**每条用例开始前**调用 Coordinator 重置。该接口只由评测 Runner 使用，
不改变日常 CLI / API 的多轮短期记忆行为。新增回归测试验证 3 条 suite 用例会执行 3 次重置。

```text
.\.venv\Scripts\python.exe -m pytest tests\test_runner.py tests\test_experiment_conditions.py tests\test_eval_memory_isolation.py -q
18 passed in 5.35s
```
