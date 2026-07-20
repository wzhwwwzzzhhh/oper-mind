# Step 1 — 双模型真实评测配置

> 日期：2026-07-18
> 快照：工作区未提交；对应 `design.md` §2-§5。

## Design

真实模型主实验需要避免“同一模型既回答又自评”的偏差。诊断模型与裁判模型均使用 OpenAI 兼容接口，
因此沿用 `LLMClient`，仅在配置、装配和 Runner 注入点分离。

## Code

- `config/config.example.yaml`：新增 `judge_llm` 模板与六个环境变量说明。
- `src/config.py`：读取并校验两套模型配置；`load_config(require_judge_llm=True)` 强制裁判配置完整。
- `src/core/bootstrap.py`：新增 `build_judge_llm()`。
- `src/eval/runner.py`：`run_case` / `run_suite` 显式接收 `judge_llm`，只把它交给 `judge_report`。
- `scripts/run_eval.py`：mock 继续使用诊断 LLM 触发 stub；真实模式装配裁判 LLM，并在 meta/config hash 记录 `judge_model`。
- `tests/test_eval_config.py`：覆盖环境变量、缺失裁判配置与裁判模型改变实验指纹。

## Test

先运行新增配置测试，未实现时预期失败：

```text
TypeError: load_config() got an unexpected keyword argument 'require_judge_llm'
```

实现后的针对性回归将覆盖配置、Runner 和 Judge；真实 API smoke 需由用户填写本地配置后另行执行，
以避免在开发过程中消耗 API 用量。

## Review

- 同一 DeepSeek API Key 可以同时填写到两个配置段；论文中仍应明确诊断模型与裁判模型名。
- 建议裁判模型名不同于诊断模型名；若暂时相同，系统允许运行但 meta 会如实记录。
- `config.local.yaml` 被忽略，不会被纳入提交。
