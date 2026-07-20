# M5 Step4 — 对比实验与指标

> 状态：⚪ 计划（待开工时填写）

## 目标

在区分度集上跑 `single_agent` vs `full`（及按需消融组），产出对比结果 + token/延迟代价。

## 计划改动文件

- `src/core/llm.py` —— 增加 token 用量采集（当前无）。
- `src/eval/metrics.py` —— 汇总 token/延迟，按场景/难度分层。
- `scripts/run_eval.py` —— 跑多 arm 对比批次，落盘 `experiments/<config_hash>/`。
- `experiments/` —— 结果产物（对比曲线数据供 M7 前端看板消费）。

## 待填

- [ ] 对比矩阵（arm × 数据集切片）
- [ ] 结果表 + 分层解读（尤其复合/跨源 vs 单域）
- [ ] 结论：多 Agent 在哪类场景有收益、代价多少
