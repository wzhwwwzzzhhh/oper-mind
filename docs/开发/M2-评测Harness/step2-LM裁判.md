# M2 step2 — LM-as-judge（`src/eval/judge.py`）

> 里程碑：M2　|　分支：`feat/m2-harness`
> 关联设计：`design.md` §4.2、决策 1（指标分两层）

## 1. 要解决的问题

确定性指标（step1）只能验证路由/机制是否触发，不能回答"诊断结论对不对"。
这是论文核心卖点（多智能体 vs 单模型质量差异）真正要靠的指标，需要一个
裁判组件，对照 golden 字段给报告打分。

## 2. 方案

`judge_report(llm, report, case) -> dict`，返回：

```python
{
    "method": "mock_stub" | "llm_judge",
    "root_cause_score": float,      # 0.0-1.0
    "key_points_recall": float,     # 0.0-1.0
    "key_points_hit": list[str],    # 命中的 golden_key_points 子集
}
```

两条路径，由 `llm.client.api_key == "mock"` 分流（复用 `src.core.graph._is_mock` 同款判断，
保持与运行时路由判断同源）：

- **mock_stub**：不调 LLM，纯字符串重合度。
  - `root_cause_score`：report 与 golden_root_cause 的字符 2-gram Jaccard 相似度。
  - `key_points_recall`：逐条检查 golden_key_points 是否作为子串出现在 report 中，
    命中数 / 总数。
  - 目的：mock 模式下 judge 环节仍可跑通（管道冒烟用），但不代表真实质量评分。
- **llm_judge**：调 `llm.chat()`，prompt 要求裁判返回 JSON
  `{"root_cause_score": float, "key_points_hit": [...]}`，用
  `src.core.graph._extract_json` 同款正则抠取（同源复用，不重复实现）。
  - `key_points_recall` 由抠出的 `key_points_hit` 反推：
    `len(命中且在golden里的) / len(golden_key_points)`。
  - **过滤幻觉**：LLM 可能报出不在 golden_key_points 里的项，一律丢弃，
    只认可真实存在于 golden 里的命中，防止裁判打分虚高。
  - **解析失败兜底**：JSON 抠取失败时返回全 0 分（而非报错中断整条 pipeline），
    保证 harness 跑批时单条裁判失败不影响其他用例。

## 3. 关键代码

```python
def judge_report(llm, report: str, case: EvalCase) -> dict:
    if _is_mock(llm):
        return _mock_stub_judge(report, case)
    return _llm_judge(llm, report, case)
```

mock stub 用 2-gram Jaccard 而非简单子串匹配 root_cause，因为 golden_root_cause
通常是完整病句而非报告里会原样出现的短语；key_points 反而更适合子串匹配，
因为设计时就要求 key_points 是可能被诊断文本直接引用的短语。

## 4. 测试

`tests/test_judge.py`，7 条，覆盖：

- mock stub 返回合法范围、全部命中、部分命中（recall=1/3）、根因关键词重合对比
- 真 LLM 路径：JSON 解析打分、JSON 解析失败兜底 0 分、命中列表过滤非法项

```
7 passed in 1.05s
```

## 5. 审查

- [x] mock 模式零 LLM 调用（judge 走 stub，不触发 `llm.chat`）
- [x] 真 LLM 路径与 mock 路径返回结构一致（下游 runner 不需要分支处理）
- [x] 幻觉命中项被过滤，不会虚高打分
- [x] 单条裁判失败不中断整批（JSON 解析失败兜底 0 分而非抛异常）
- [x] 复用 `_is_mock` / `_extract_json`，与 graph.py 运行时判断同源
- [x] 7/7 测试通过

无遗留问题。下一步 step3：runner + result_schema，把 metrics + judge 接到真实 pipeline 上跑批。
