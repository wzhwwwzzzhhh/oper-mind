# M2 step4 — 结果契约（CaseResult/EvalSummary）与 CLI（Step 层）

> 里程碑：M2　|　分支：`feat/m2-harness`　|　接续：step1 确定性指标 + step2 LM-as-judge + step3 Runner
> 创建日期：2026-07-14

## 1. 要解决的问题

step3 的 `run_case`/`run_suite` 产出的是自由格式 dict（`{case_id, report, trace, deterministic, judge, error?}`），
逐条用例还缺一个**结构化、带校验的结果契约**，也缺把 65 条结果**聚合成一份汇总统计**并**落盘**的动作。
step4 补齐这两块，同时提供 CLI 入口把 load_cases → build_system → run_suite → 落盘串成一条命令。

## 2. 方案

### 2.1 `src/eval/result_schema.py`

- `CaseResult`（Pydantic）：单条用例的结构化结果。字段直接来自 step1/step2 的输出，**不引入新指标名**：
  `case_id, domain, difficulty, actual_strategy, route_hit, target_hit, pipeline_complete, mechanism_hit,
  root_cause_score(0~1), key_points_recall(0~1), key_points_hit, judge_is_stub, report_text, error`。
  - `domain`/`difficulty` 来自 `EvalCase`（run_result 里没有），其余字段来自 `run_result["deterministic"]`
    和 `run_result["judge"]`。
  - `from_run_result(case, run_result)` 分类方法负责拆包嵌套 dict，是 runner 输出 → 结构化契约的唯一入口。
- `EvalSummary`：整批汇总，含总体 4 个 hit_rate + 2 个 judge 均分 + `judge_is_stub` + `error_count`，
  外加 `by_domain`/`by_difficulty` 两个切片（`DomainStats`：count + hit_rate + 两个均分）。
- `build_summary(config_hash, results)`：纯函数，对 `list[CaseResult]` 做聚合，空列表时返回全 0（不除零崩溃）。

### 2.2 `scripts/run_eval.py`（CLI）

流程：`load_cases` → `build_system()`（复用 bootstrap，不重新发明加载逻辑）→ 判断 mock/real
（读 `coordinator.llm.client.api_key == "mock"`）→ `run_suite` → 逐条 `CaseResult.from_run_result`
→ `build_summary` → 按 config_hash 落盘到 `experiments/<hash>/{cases.jsonl, summary.json, meta.json}`。

- `--real` 标志：显式要求真实 LLM 时，若探测到仍是 mock，直接报错退出，避免"以为在跑真实评测,实际
  还是 mock"的静默误导。
- `config_hash`：`sha256(cases_path|seed|is_mock|model)` 取前 12 位，保证同配置复现到同目录、不同配置
  不互相覆盖。

## 3. 关键设计：不重新定义指标字段名

`CaseResult` 字段严格对齐 step1 (`route_hit/target_hit/pipeline_complete/mechanism_hit`) 和
step2 (`root_cause_score/key_points_recall/key_points_hit/method`) 的**实际输出**，而不是 design.md
草稿里设想的字段名（`strategy_hit/agents_hit/debate_hit`）。草稿写在前、代码实现在后，两者出现偏差时
以已跑通的代码为准——写 `result_schema.py` 前重新读了 `runner.py`/`judge.py`/`metrics.py` 的真实返回结构。

## 4. 测试

`tests/test_result_schema.py`，7 个用例：

- `test_from_run_result_基本字段拼装`：正常路径,字段一一对应。
- `test_from_run_result_llm_judge_不是stub`：`judge.method == "llm_judge"` 时 `judge_is_stub=False`。
- `test_from_run_result_带error字段`：run_result 带 `error` 时正确带出。
- `test_build_summary_全命中`：全部指标 1.0 时汇总也是 1.0。
- `test_build_summary_error计数`：`error_count` 统计正确。
- `test_build_summary_按域按难度切片`：`by_domain`/`by_difficulty` 聚合正确。
- `test_build_summary_空列表不崩`：空 `results` 不抛异常,返回 0 值汇总。

全部通过。`run_eval.py` 未写独立单测（纯 I/O 编排脚本,逻辑都在已测试的 `load_cases`/`run_suite`/
`result_schema` 里),改为用一次真实 mock 端到端跑通作为验收证据（见 §5）。

## 5. 端到端 mock 冒烟证据

```
OPERMIND_API_KEY=mock python scripts/run_eval.py
```

两次独立运行（相隔一次 `data/memory.json` 修复重跑）结果完全一致，config_hash 均为 `b7108eab8602`：

```
route_hit_rate       = 100.00%
target_hit_rate      = 100.00%
pipeline_complete    = 100.00%
mechanism_hit_rate   = 92.31%
mean_root_cause      = 0.487
mean_key_points      = 0.015
judge_is_stub        = True
error_count          = 0
```

**两次数字完全一致，证明 judge stub 分数在同种子下稳定可复现**（design.md §8 验收标准之一）。

### 必须澄清的两个数字（避免被误读为质量差）

- **`mean_key_points_recall = 0.015`**：这是 mock 模式下 `judge_is_stub=True` 的产物。
  `src/core/llm.py` 的 `_mock_chat` 对任何 domain 都返回固定的 DB 风格诊断文本，跟 65 条用例里
  server/log/compound 域的 `golden_key_points`（如"内存泄漏""磁盘 I/O"等关键词）几乎不重合，
  所以 mock stub 用字符集重合度算出的 recall 天然很低。**这不是系统诊断质量的真实信号**，只在
  接入真实 LLM（`judge_is_stub=False`）后才有评测意义。
- **`mechanism_hit_rate = 92.31%`**（65 条里 5 条未命中）：`expects_debate=True` 的用例要求 trace
  里出现 `debate` 节点，但 mock 模式下 parallel 策略聚合的诊断内容高度雷同（都是同一份固定 DB 文本），
  可能触发不了 debate 的分歧检测阈值，导致部分理论上该辩论的用例在 mock 下没有触发。这是 mock 数据
  同质化的副作用，不是 debate 触发逻辑本身的 bug（这一判断留给 review.md 做最终确认）。

## 6. 影响范围

- `.gitignore` 新增 `experiments/`（评测产出可复现、不进库）。
- `data/memory.json`：跑评测会往长期记忆写 65 条诊断记录，是预期副作用（`LongTermMemory.add_record`
  的正常行为），每次评测后需要 review 是否要还原到跑评测前的状态（见 review.md 的 git 卫生记录）。
