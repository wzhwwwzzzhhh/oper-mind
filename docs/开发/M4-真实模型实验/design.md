# M4 设计 — 真实模型主实验

> 里程碑：M4　|　分支：`feat/m2-harness`
> 创建日期：2026-07-18

## 1. 目标

M4 以真实模型进行主实验。诊断模型负责生成运维报告，独立裁判模型依据 golden 根因与关键点打分；
两者可共用同一 DeepSeek API Key，但配置、模型名和实验元数据必须分离，避免将被测模型静默复用于评分。

## 2. 配置契约

`config.local.yaml` 和环境变量支持两组配置：

- `llm` / `OPERMIND_API_KEY`、`OPERMIND_BASE_URL`、`OPERMIND_MODEL`：被测诊断模型。
- `judge_llm` / `OPERMIND_JUDGE_API_KEY`、`OPERMIND_JUDGE_BASE_URL`、`OPERMIND_JUDGE_MODEL`：裁判模型。

mock 运行只需诊断模型为 `mock`，保持确定性 `mock_stub` 打分。真实运行会要求 `judge_llm` 的
`api_key`、`base_url`、`model` 全部存在；缺失时在发起任何评测请求前报错。

## 3. 数据流

```text
EvalCase → Coordinator(诊断 llm) → Report
                              ↓
                    judge_llm + golden 答案 → quality scores
                              ↓
                cases.jsonl / summary.json / meta.json
```

`meta.json` 记录 `model`、`judge_model`、`arm`、`seed` 和 `is_mock`。`config_hash` 同时包含
诊断模型与裁判模型，确保改变任一评分条件都会落入不同实验目录。

## 4. Step 2 评分口径校准

在正式运行 65 条真实主实验前，真实 LLM Judge 的关键点命中从“返回原文再严格字符串匹配”改为
“返回 golden 关键点 ID，再由程序映射回原文”。该改动解决语义正确但措辞不同导致召回为零的问题。
具体契约、边界、测试与人工抽检标准见 `step2-评分口径校准与关键点ID判定.md`。

## 5. Step 3 实验条件与可比指标

真实主实验的 6 个实验组、单 Agent 公平基线、三次 replicate、端到端 latency 和按条件解释的
condition_complete，见 `step3-实验条件切换与可比指标.md`。该步骤完成后才可启动 M4 正式批量实验。

## 6. 本步范围

本步只搭建双模型真实评测配置与可追溯性，不实现 M4 的 baseline/路由/Debate/Reflection 消融开关；
这些实验条件将在后续 M4 Step 中独立设计，确保一次只改变一个变量。

## 7. 验收

- mock 回归继续可运行，无需配置 `judge_llm`。
- 两组环境变量分别覆盖 YAML 中的诊断与裁判配置。
- 真实评测缺少裁判配置时有明确失败信息。
- `meta.json` 记录裁判模型，且裁判模型变化导致不同 config hash。
- 不在代码、示例文件或开发日志中写入真实 API Key。
