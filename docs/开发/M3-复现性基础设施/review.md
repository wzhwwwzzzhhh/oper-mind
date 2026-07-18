# M3 Review — 复现性基础设施

> 审查日期：2026-07-18
> 审查快照：工作区未提交；目标提交信息建议为 `feat: M3复现性基础设施与统计检验`。

## 1. 变更范围

| 范围 | 结果 |
|---|---|
| 温度确定性 | `src/core/llm.py`、`src/core/debate.py`、`src/agent_langgraph.py` 的 M3 改动均将默认或显式温度统一为 `0.0`。 |
| 依赖锁定 | `requirements.txt` 已按 Python 3.11.9 实测环境锁定直接依赖版本，并补齐 `numpy`、`scipy`、`pytest`、`psutil`。 |
| 统计能力 | `src/eval/stats.py` 提供描述统计、Wilcoxon、Friedman 和 JSONL 指标读取；`tests/test_stats.py` 覆盖核心行为。 |
| 实验组标记 | `scripts/run_eval.py` 增加 `--arm`，同时写入 config hash 与 `meta.json`。 |
| 评测隔离 | `scripts/run_eval.py:63-64` 关闭长期记忆；`src/core/agent.py:19-110` 不读取、不写入长期记忆，防止用例顺序污染。 |
| 测试卫生 | `tests/test_diagnosis.py:21-63` 不再从 pytest 测试函数返回布尔值，已清除 warning。 |
| 规范同步 | `AGENTS.md:77` 与 `docs/开发规范.md:55` 已增加评测长期记忆隔离约束。 |

## 2. 验收证据

### 2.1 自动化回归

```text
.\.venv\Scripts\python.exe -m pytest tests -q
34 passed in 3.53s
```

- 覆盖新增 `tests/test_stats.py` 和 `tests/test_eval_memory_isolation.py`。
- 输出无 pytest warning。

### 2.2 质量 pipeline 回归

```text
.\.venv\Scripts\python.exe scripts\smoke_pipeline.py
✅ 三条路径全部跑通,pipeline 已接通(route → agent → [debate] → report → reflection)
```

- direct、chain、parallel 三条路径均通过 report 与 reflection。
- 人工制造的并行结论分歧触发 debate 节点。
- 脚本运行后恢复 `data/memory.json`，SHA-256 与运行前一致：
  `FA502DECEBD6D0F9DEE3AF2DF95A8458B755D14146115E6EAC7B31E1A161A475`。

### 2.3 mock 评测产物

```text
.\.venv\Scripts\python.exe scripts\run_eval.py --arm m3-smoke --seed 42
```

- `experiments/1652cc7cc4ea/meta.json`：`arm="m3-smoke"`、`is_mock=true`、`seed=42`、
  `total_cases=65`。
- `cases.jsonl` 共 65 行，`error_count=0`。
- 评测前后 `data/memory.json` 校验值一致，证明评测用例不再读写长期记忆。
- `load_metric(..., "root_cause_score")` 成功读取 65 个 case；`describe()` 输出均值、标准差和 95% CI。

## 3. 验收标准核对

| M3 标准 | 结论 |
|---|---|
| 全量 `pytest tests/` 通过 | 通过：34 passed。 |
| 真实模式同 query 两次输出一致 | 待人工 smoke：会调用用户的真实模型服务并产生用量。mock 主实验不受阻塞。 |
| 精确 requirements 且环境可装可测 | 通过：依赖已依据 Python 3.11.9 环境锁定；用户执行安装并已报告测试通过。 |
| stats 三类统计函数有独立测试 | 通过。 |
| `--arm` 生效且 meta 带 arm | 通过。 |
| 评测样例互相隔离 | 通过：有红绿测试与 `memory.json` 哈希验证。 |

## 4. 风险与后续

1. **真实模型复核仍待执行**：在确认真实 API 配置和可接受用量后，对同一 query 连跑两次，保留两份输出及模型 ID 作为温度为 0 的人工证据。
2. **mock 质量分数不是论文结论**：本轮为 M3 基础设施验证；mock judge 仍标记为 `judge_is_stub=true`。M4 才应对比 baseline、debate、reflection 等实验组并做显著性检验。
3. **实验脚本之外的长期记忆**：日常 CLI/API 保留长期记忆是设计意图；若以后新增其他批量评测入口，也必须显式关闭它。

## 5. 审查结论

M3 的 mock 主实验复现基础已闭环：依赖版本、种子与实验组元数据、统计函数、评测样例隔离、全量测试和 pipeline 回归均有可追溯证据。下一阶段应进入 M4：定义可切换的实验条件并生成论文用对比表与显著性检验结果。
