# M5 Step1 — 评测口径修复

> 状态：✅ 完成（2026-07-20）
> 分支：`feat/m5-agent-comparison`　|　方案：A（stub 定位为管路工具，非质量信号）

## 背景

`src/eval/judge.py` 的 mock stub 有两处假信号：

- `key_points_hit` 用 `point in report` 做**整句精确子串匹配**——报告不可能逐字复现 golden 短语（如 `"orders.status 无索引"`），导致 `key_points_recall` 结构性趋近 0（历史实测 0.015）。
- `root_cause_score` 用 `set(中文串)` 拆成**单字**算重合——被高频字撑起来，是噪声。

## 方案（A）

承认 **stub 只是管道联通/冒烟工具，分数不是质量信号**；质量结论一律以真实 LLM 裁判（`_llm_judge`，走裁判选的 KP 编号）为准。同时把 stub 从「整句精确匹配」换成「词元级重合」，让冒烟数字可读、不再是吓人的 0.015。

## Code 改动

`src/eval/judge.py`：

- 新增 `import re` + 常量 `_STUB_HIT_RATIO = 0.5`。
- 新增 `_tokenize(text)`：按空白与中英文标点切词。
- 重写 `_mock_stub_judge`：
  - 根因分数 = golden 根因词元在报告中出现的比例（替代单字集合重合）。
  - 关键点命中 = 该点词元**过半出现**（≥ `_STUB_HIT_RATIO`）即记命中（替代整句精确匹配）。
  - docstring 显式标注「本 stub 分数非质量信号，以 `_llm_judge` 为准」。
- 真实裁判路径 `_llm_judge` 未改动。

关键片段（`src/eval/judge.py` `_mock_stub_judge`）：

```python
key_points_hit: list[str] = []
for point in case.golden_key_points:
    tokens = _tokenize(point)
    if not tokens:
        continue
    hit_ratio = sum(1 for tok in tokens if tok in report) / len(tokens)
    if hit_ratio >= _STUB_HIT_RATIO:
        key_points_hit.append(point)
```

## Test 证据

`tests/test_judge.py` 新增 2 条：

- `test_mock_stub_多词元关键点过半即命中`：`"orders.status 无索引"` 在措辞不同的报告中命中（旧版整句匹配会漏判）。
- `test_mock_stub_词元不足半数不算命中`：4 词元只命中 1 个 → 低于阈值 → 不记命中。

原有 mock/真实裁判用例全部保留且通过（关键点为单词元时行为不变）。

```text
python -m pytest tests/test_judge.py -q   →  13 passed
python -m pytest -q                        →  57 passed（M4 为 55，+2 新测试）
python scripts/smoke_pipeline.py           →  退出码 0，三路径 + debate 全跑通
```

## 结论与已知限制

- 假信号消除：stub recall 不再结构性归零，且代码层面明确其非质量信号定位。
- **限制**：stub 仍是粗粒度词元重合，不作质量结论；真实的「多 Agent vs 单模型」对比必须用真实 LLM 裁判跑（M5 step4）。
- 尚未重跑历史 `experiments/`（旧产物用旧口径，保留作对照即可，不覆盖）。
