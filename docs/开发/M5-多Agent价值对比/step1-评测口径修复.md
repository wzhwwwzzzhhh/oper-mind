# M5 Step1 — 评测口径修复

> 状态：⚪ 计划（待开工时填写 Code/Test 细节）

## 背景

`src/eval/judge.py:20` 的 mock stub 用 `point in report` 做**整句精确子串匹配**，报告不可能逐字复现 golden 短语，导致 `key_points_recall` 结构性趋近 0（实测 0.015，假信号）；`judge.py:16-18` 的 root_cause_score 用 `set(中文串)` 拆单字算重合，是噪声。

## 计划改动文件

- `src/eval/judge.py` —— 把 `_mock_stub_judge` 的整句匹配改为**词级/关键片段重合**（或明确标注 stub recall 不可比、主实验只信真实裁判）。
- `tests/test_judge.py` —— 补对应用例。
- 重跑 `experiments/` 验证数字变化可解释。

## 待填

- [ ] 口径方案定稿（词级重合阈值 vs 仅真实裁判可比）
- [ ] Code 片段 + `文件:行号` 锚点
- [ ] Test Evidence
