# M2 step3 — 评测 Runner（Step 层）

> 里程碑：M2　|　分支：`feat/m2-harness`　|　接续：step1 确定性指标 + step2 LM-as-judge
> 创建日期：2026-07-14

## 1. 要解决的问题

step1/step2 分别产出了「读 trace 算命中」和「读报告打分」两个纯函数，但还没有东西把它们跟真实
coordinator 串起来、批量跑完 65 条用例并逐条落盘结果。这就是 runner 的职责：驱动、串联、隔离失败。

## 2. 方案

`src/eval/runner.py` 提供两个函数：

- `run_case(coordinator, llm, case) -> dict`：跑单条用例。
  1. 调 `coordinator.route(case.query)` 拿报告文本；
  2. 调 `coordinator.get_trace()` 拿链路事件流；
  3. 把 trace 喂给 `compute_deterministic`（step1），报告喂给 `judge_report`（step2）；
  4. 汇总成一条结果记录：`{case_id, report, trace, deterministic, judge}`。
- `run_suite(coordinator, llm, cases) -> list[dict]`：遍历用例集，逐条调 `run_case`。

**只依赖 coordinator 的两个公开接口**（`route(query) -> str`、`get_trace() -> list[dict]`，
见 `src/core/coordinator.py`），不关心其内部实现，因此单测用一个假 coordinator 完全隔离，不需要
真实 LLM 或 Agent。

## 3. 关键设计：单条失败不中断整批

`coordinator.route()` 可能抛异常（真实环境里 LLM 超时、Agent 出错等都可能发生）。`run_case` 内部
用 `try/except` 包住调用：

- 失败时 `report=""`、`trace` 用 `get_trace()` 的返回值（可能为空列表)、并记录 `error` 字段；
- `deterministic`/`judge` 仍会基于空 trace / 空报告算出（`route_hit=False` 等），保证返回结构
  始终一致，下游汇总代码不用特判「这条用例是不是崩了」。

`run_suite` 因此天然具备「一条崩溃不影响其他用例」的性质——不需要在 `run_suite` 层面加额外的
try/except，异常已经在 `run_case` 内被吞掉。

## 4. 测试

`tests/test_runner.py`，5 个用例：

- `test_run_case_返回结构`：正常路径,验证 deterministic/judge 字段都对。
- `test_run_case_把query传给coordinator`：确认 `case.query` 被原样传给 `coordinator.route()`。
- `test_run_case_异常不中断_返回error字段`：coordinator 抛异常时,返回结构仍完整,含 `error`。
- `test_run_suite_遍历全部用例`：3 条用例都被跑到,`received_queries` 长度对。
- `test_run_suite_单条失败不影响其他用例`：用一个「第二次调用必崩」的假 coordinator,验证
  第一条结果正常、第二条带 `error`,总数不少。

全部通过；额外跑了全量回归 `pytest tests/`（19 个用例,含 M0/M1 遗留测试）全绿,确认未引入回归。

## 5. Review

- 契约来源：本次严格遵守「先读测试真实内容(grep 核对 + Read 交叉验证),再实现」的流程,
  一次性写对 runner.py,没有出现 step1 时的契约错配问题。
- 设计合理性：runner 不依赖 coordinator 具体类型,只靠接口契约,面向真实 LLM/Agent 环境时
  可以无缝替换假 coordinator 为 `bootstrap.build_system()` 产出的真实实例。
- 遗留:runner 目前是同步逐条跑,65 条用例在 mock 模式下够快;若后续换真实 LLM,可能需要
  加并发或进度输出,留给 step4/M4 视实际耗时决定。
- 结论:**通过**,可提交。
