# M4 Step 2 Review — Judge 关键点 ID 口径

> 审查日期：2026-07-18
> 审查快照：工作区未提交；覆盖 `step2-评分口径校准与关键点ID判定.md`。

## 结论

真实 Judge 的关键点评分已从原文逐字匹配改为 golden 编号选择，解决了语义/措辞不同导致
`key_points_recall` 被错误置零的问题。下游 `CaseResult` 与 `cases.jsonl` 仍保留原始关键点文本，
不需要迁移历史评测结构。

## 实现核对

- `src/eval/judge.py`
  - prompt 为每个 golden 关键点提供 `KP1...KPN`；
  - 仅接收 `key_point_ids`，过滤非法值并按首次出现顺序去重；
  - 映射回 `key_points_hit` 原文，保持既有 Runner / Schema 接口；
  - 根因分数安全转换并裁剪到 `[0.0, 1.0]`；
  - mock stub 未改变。
- `tests/test_judge.py`
  - 覆盖 ID 映射、非法/重复 ID、非列表 ID、JSON 失败和越界/非数值分数；
  - mock 路径测试继续保留。

## 验收证据

```text
.\.venv\Scripts\python.exe -m pytest tests\test_judge.py -q
11 passed in 0.98s
```

真实 `db-001` smoke：`root_cause_score=1.0`、`key_points_recall=1.0`，命中全部三条
黄金关键点，无运行错误。

## 剩余门槛

正式运行 65 条真实主实验前，仍需完成 Step 2 文档定义的 12 条人工抽检：DB / Server / Log /
Compound 各 3 条，人工与 Judge 命中集合至少 10 条完全一致。未达标时先修订 Judge prompt 或
数据集 golden，再重新抽检。
