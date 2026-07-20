# Step 2 — LLM-as-Judge 评分口径校准与关键点 ID 判定

> 日期：2026-07-18
> 快照：工作区未提交；对应 `design.md` 的真实模型评测链路，服务 M4 主实验前的评分口径校准。

## Design

### 问题与根因

真实 smoke 中，`db-001` 的 `root_cause_score=1.0`，但 `key_points_recall=0.0`。根因不是报告
没有命中关键点，而是现有 `src/eval/judge.py` 要求裁判返回的 `key_points_hit` 文本与
`golden_key_points` **逐字完全一致**。真实 LLM 即使用语义等价表达，也会被程序过滤为未命中，导致
关键点召回被系统性低估。

### 目标契约

真实 LLM Judge 不再输出关键点原文，而是输出 golden 列表的编号：

```text
KP1, KP2, ... KPN
```

Prompt 在每个 golden 关键点前展示固定编号，并要求只返回如下 JSON：

```json
{
  "root_cause_score": 0.0,
  "key_point_ids": ["KP1", "KP3"]
}
```

程序将合法且去重后的 `key_point_ids` 映射回原始 `golden_key_points`，保持对下游
`CaseResult.key_points_hit: list[str]` 的既有接口不变。召回率仍定义为：

```text
去重后的合法命中数 / golden_key_points 总数
```

### 边界与失败策略

- `root_cause_score`：解析为 float 后裁剪到 `[0.0, 1.0]`；缺失、非数值或 JSON 解析失败时为 `0.0`。
- `key_point_ids`：只接受列表；非列表、缺失或 JSON 解析失败时视为空列表。
- 非法 ID：忽略，例如 `KP99`、`foo`、空串。
- 重复 ID：去重，首次出现顺序有效，不重复计分。
- `EvalCase` Schema 已保证 golden 关键点非空；Judge 不额外放宽该数据契约。
- mock judge：保持现有关键词重合逻辑与返回格式，不改评分口径。
- 向后兼容：真实 Judge 的旧字段 `key_points_hit` 不再作为输入契约；若裁判返回旧字段但无
  `key_point_ids`，按空命中处理，以避免重新引入逐字匹配歧义。

### 人工抽检校准

关键点 ID 契约实现后，真实模型主实验前抽取 **12 条**用例：DB / Server / Log / Compound 各 3 条，
覆盖 easy / medium / hard。对每条报告，由人工按 golden 关键点独立标注命中项，再与 Judge 的
`key_points_hit` 对比，记录：

- 每条的 `case_id`、人工命中 ID、Judge 命中 ID；
- 一致 / 不一致；
- 不一致原因（漏判、误判、golden 歧义、报告确实未覆盖）。

验收标准：12 条中至少 10 条人工与 Judge 的“命中集合”完全一致；若不足 10 条，先修订 Judge prompt
或 golden 关键点，再重新抽检，禁止直接跑 65 条正式主实验。

## Step

1. 将真实 Judge prompt 的关键点改为 `KP{id}: 原始文本` 格式，输出字段改为 `key_point_ids`。
2. 增加私有 ID 映射与解析逻辑：编号映射、顺序去重、非法编号过滤、分数裁剪。
3. 保持 `judge_report()` 的返回结构不变，确保 `runner.py`、`result_schema.py` 和历史 JSONL 契约无需修改。
4. 用 fake LLM 完成单元测试后，运行一次真实 `db-001` smoke，确认根因得分正常且关键点召回不再因措辞差异被置零。
5. 完成 12 条人工抽检，结果写入后续 Step 2 Test / Review 快照；正式 65 条主实验只在抽检达标后启动。

## Code

计划修改：

- `src/eval/judge.py`
  - 新增关键点 ID 格式化、ID 解析和安全分数规范化的私有函数。
  - 修改 `_llm_judge()` 的 prompt 与 JSON 解析。
- `tests/test_judge.py`
  - 真实 Judge 路径改为断言 ID 输出映射；补充非法、重复、缺失、越界分数与空 golden 等边界。
- `docs/开发/M4-真实模型实验/review.md`
  - 实现后记录真实 smoke 与人工抽检结论。

不修改：

- `data/eval/cases.jsonl` 的 `golden_key_points` 原文；
- `src/eval/result_schema.py` 的落盘字段；
- mock judge 的确定性评分逻辑。

## Test

### 单元测试（先红后绿）

1. Judge 输出 `{"root_cause_score": 0.8, "key_point_ids": ["KP1"]}` 时，命中映射为第一个 golden 文本，召回率正确。
2. 输出 `["KP1", "KP1", "KP99", "foo", "KP2"]` 时，仅保留 KP1、KP2 且不重复计分。
3. `key_point_ids` 为字符串 / null / 缺失时，召回率为 0，不抛异常。
4. 根因分数为 `1.5`、`-0.2`、`"bad"` 时，分别得到 `1.0`、`0.0`、`0.0`。
6. mock stub 的已有三个测试保持通过，确认本步未改变 mock 评测口径。

### 集成 smoke

填写真实诊断和裁判模型配置后，运行 `db-001`：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_judge.py -q
```

随后用 `run_case()` 跑 `db-001`，记录 `judge_method=llm_judge`、`root_cause_score`、
`key_points_recall` 与 `key_points_hit`。不得打印 API Key。

## Review

- 本步骤只校准 Judge 的关键点口径，不改变诊断模型、路由策略、Debate、Reflection 或工具集。
- 实验时诊断模型和裁判模型当前都可使用 `deepseek-v4-flash`，但其角色与元数据必须保持分离。
- 真实模型主实验成本由用户承担；任何 65 条全量真实评测前必须先完成 12 条人工抽检。
- 真实 API 不稳定、限流或认证失败时不得将 0 分混入实验结论；须记录失败 case，并在同配置下单独重跑。

## Test Evidence

### 红灯

在实现前，替换真实 Judge 测试契约后运行：

```text
.\.venv\Scripts\python.exe -m pytest tests\test_judge.py -q
6 failed, 6 passed
```

失败原因与设计一致：旧实现只能解析 `key_points_hit` 原文，不能映射 `key_point_ids`，不去重或过滤非法
ID，不裁剪越界分数，且非数值分数会抛出 `ValueError`。

### 绿灯

实现关键点 ID 映射、顺序去重、非法 ID 过滤与分数归一化后：

```text
.\.venv\Scripts\python.exe -m pytest tests\test_judge.py -q
11 passed in 0.98s
```

### 真实 smoke

2026-07-18 使用真实诊断模型与真实裁判模型运行 `db-001`：

```text
actual_strategy=direct
judge_method=llm_judge
root_cause_score=1.0
key_points_recall=1.0
key_points_hit=["orders.status 无索引", "type=ALL 全表扫描", "建议加 idx_status"]
error=None
```

该结果验证裁判已按 `key_point_ids` 选择 golden 项并由程序映射回原文，消除了旧实现中
“根因满分但关键点召回为零”的逐字匹配偏差。
