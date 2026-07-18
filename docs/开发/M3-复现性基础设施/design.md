# M3 设计 — 复现性基础设施

> 里程碑：M3　|　分支：`feat/m2-harness`（沿用，待 M2 已合并逻辑上视为基线）
> 创建日期：2026-07-14
> 路线图原文（`docs/开发路线图与规划.md`）："M3 复现性：固定种子；主实验跑 mock 模式（确定性）；
> `src/eval/stats.py`（均值/标准差/95%CI/Wilcoxon/Friedman）；锁依赖版本；温度设 0。"

## 1. 要解决的问题

M2 的 harness 能跑通单次评测并给出汇总数字，但论文需要的是**跨条件对比的统计结论**（比如"多智能体
debate 相对单 Agent 直答，root_cause_score 显著更高"），这需要：
1. 多次实验运行的结果可比（同配置复现出同数字，不同配置的差异不是噪声）；
2. 有工具把两组/多组实验结果做配对统计检验，而不是肉眼比较汇总数字。

M3 就是补这两块地基，不产出任何实验结论本身（那是 M4 的事）。

## 2. 现状核查（读代码确认,不是假设）

- **种子当前是摆设**：`scripts/run_eval.py` 调了 `random.seed(args.seed)`，但全仓库搜
  `random\.<method>` 的真实调用点为零——mock 模式的 `_mock_chat`（`src/core/llm.py:61-114`）是纯字符串/
  关键词逻辑，路由（`src/core/coordinator.py`）也不掺随机。**mock 主实验的确定性来自"没有随机源"，
  不是来自"随机源被种子锁住"**。`--seed` 目前只进了 config_hash 指纹和 `meta.json`，起的是"标注这次
  跑的是哪个配置"的作用，不是真的在锁什么随机行为。
- **温度三处不一致**：`src/core/llm.py:15` 默认 `temperature=0.1`；`src/agent_langraph.py:96` 另起一份
  `ChatOpenAI` 硬编码 `0.1`；`src/eval/judge.py`/`src/core/graph.py` 的部分调用点显式传 `0.0`；
  但 `debate.py:77` 传 `0.1`，`agent.py`/`debate.py`/`graph.py`/`reflection.py` 的其余调用点不传参数，
  落到 `0.1` 的默认值。**真实 LLM 模式下同一条 query 两次跑，数字很可能不一致**——这是 M3 要修的真问题。
- **依赖是开区间**：`requirements.txt` 全部 `>=`，无锁文件，`.venv` 当前不存在。
- **stats.py 不存在**：`numpy`/`scipy` 都不在依赖里，仓库里没有任何均值/CI/检验的代码。
- **实验目录只按 config_hash 区分,没有"实验组"概念**：`_config_hash()` 只吃
  `cases_path|seed|is_mock|model`，不包含"是否开 debate""路由策略"之类的实验条件。M4 要做组间对比时，
  今天的目录结构没法区分"这是 baseline 组"还是"这是 debate 组"的产出。

## 3. 方案

### 3.1 温度统一为 0（真实修复,不是摆设）

- `src/core/llm.py`：`LMClient.chat()` 默认 `temperature` 改为 `0.0`。
- `src/agent_langraph.py:96`：`ChatOpenAI(temperature=0.1)` 改为 `0.0`。
- `src/core/debate.py:77`：显式 `0.1` 改为 `0.0`。
- 其余隐式走默认值的调用点（`agent.py`/`reflection.py`/`graph.py` 里不传 `temperature` 的）不用逐个改，
  因为它们会自动吃到 `llm.py` 改过的新默认值 `0.0`。
- **不影响 debate 机制**：debate 的分歧来自不同 Agent 看到的上下文/工具结果不同，不是靠同一个模型多次
  采样制造随机分歧；温度置零不会让 debate"失去意义"。
- **mock 模式不受影响**：`_mock_chat` 根本不读 `temperature` 参数。

### 3.2 种子：如实文档化,不做假动作

不新增任何"用种子去控制"的代码——因为没有真实随机源需要控制。`--seed` 保留在 `run_eval.py` 里
（继续进 config_hash 指纹），但 design 文档和 review 里明确写清楚：**mock 主实验的确定性来自确定性
mock 逻辑本身,种子只是实验命名/归档的一部分,不是"锁随机数发生器"的意义上的复现性开关**。

`src/eval/stats.py` 的置信区间用**参数法**（t 分布：`mean ± t_{0.975,df} * SE`），不用 bootstrap
重采样——这样统计层本身也不引入新的随机源，不需要为它单独播种。

### 3.3 依赖锁定

在有网络/能装依赖的环境下创建 `.venv`，用当前 `requirements.txt` 的开区间约束解析出一版正确可跑的
版本组合，跑通 `pytest tests/` 全绿后，把 `requirements.txt` 里的 `>=` 全部改成 `==` 精确版本
（不引入 poetry/pipenv 这类新工具链，维持项目现有的"一个 requirements.txt"风格）。同时把新增的
`numpy`/`scipy`（见 3.4）也以精确版本形式加入。

### 3.4 `src/eval/stats.py`

新增依赖：`numpy`、`scipy`（精确版本，见 3.3）。

提供的函数（全部是纯函数，输入 `list[float]` 或两组/多组 `list[float]`，不读文件不产副作用）：

```python
def describe(values: list[float]) -> dict:
    """返回 {mean, std, n, ci_low, ci_high}，CI 用 t 分布参数法，n<2 时 CI 退化为 (mean, mean)。"""

def compare_two(a: list[float], b: list[float]) -> dict:
    """Wilcoxon 符号秩检验（配对，要求 len(a)==len(b)），返回 {statistic, p_value}。
    用于两个条件（如 baseline vs debate）在同一批用例上的配对对比。"""

def compare_many(*groups: list[float]) -> dict:
    """Friedman 检验（>=3 个配对条件），返回 {statistic, p_value}。
    用于三种及以上路由策略/机制配置的整体差异检验。"""
```

另加一个装载工具函数，从 `experiments/<hash>/cases.jsonl` 里按 `case_id` 取出某个指标
（如 `root_cause_score`）的对齐数组，供 `compare_two`/`compare_many` 使用：

```python
def load_metric(cases_path: str, metric: str) -> dict[str, float]:
    """读 cases.jsonl（CaseResult 的 JSON Lines），返回 {case_id: metric_value}。"""
```

配对检验要求两组用**同一批 case_id 按相同顺序对齐**——`load_metric` 返回 dict 而不是 list，
调用方（M4 的对比脚本）自己按共同 case_id 集合取交集、排序、转成对齐的两个 list，
这样 `stats.py` 本身不用管"两次实验用例集合是否完全一致"这类业务逻辑。

### 3.5 实验条件标注（为 M4 铺路，不在 M3 内实现对比脚本本身）

`scripts/run_eval.py` 的 `_config_hash` 增加一个可选 `--arm` 参数（默认 `"default"`），
纳入指纹计算，同时把 `arm` 字段写进 `meta.json`。这样 M4 起多组对比实验时
（如 `--arm baseline` vs `--arm debate`），产出目录天然分开、`meta.json` 里能直接看出这次跑的是哪组，
不需要额外维护一份"哈希→组名"的手工映射表。

M3 只做这一个字段的铺垂；真正跑多组对比实验、调用 `stats.py` 产出论文用的检验结果，是 M4 的工作。

## 4. 测试

- `tests/test_stats.py`：
  - `describe`：已知均值/标准差的构造数据，验证 mean/std/CI 计算正确；n=1 时 CI 不崩。
  - `compare_two`：构造"几乎一样"和"明显不同"的两组配对数据，验证 p_value 分别不显著/显著；
    长度不等时抛异常。
  - `compare_many`：构造三组配对数据，验证 p_value 合理。
  - `load_metric`：构造一个假的 `cases.jsonl`，验证按 `case_id` 取值正确。
- 温度改动：不新增单测（这是配置值改动，不是逻辑分支），靠**全量回归 `pytest tests/`**
  确认现有 mock 冒烟测试（不读 temperature）仍然全绿，外加一次真实模式的手动 smoke（同一条 query
  跑两次，人工确认输出一致）作为 review 证据。
- 依赖锁定：`pip install -r requirements.txt` 在干净 `.venv` 里成功、`pytest tests/` 全绿，
  作为"锁完的版本组合真的能跑"的验收证据。

## 5. 影响范围

- `src/core/llm.py`、`src/agent_langraph.py`、`src/core/debate.py`：默认/硬编码温度改为 0。
- `requirements.txt`：开区间 → 精确版本，新增 `numpy`/`scipy`。
- `src/eval/stats.py`（新增）、`tests/test_stats.py`（新增）。
- `scripts/run_eval.py`：新增 `--arm` 参数，`meta.json` 新增 `arm` 字段。
- 不改 `src/eval/result_schema.py`/`runner.py`/`metrics.py`/`judge.py`（M2 产出保持不变）。

## 6. 验收标准

- [ ] 全量回归 `pytest tests/` 通过（含新增 `test_stats.py`）
- [ ] 真实模式下同一条 query 跑两次，输出一致（温度 0 生效的证据）
- [ ] `requirements.txt` 全部精确版本，干净 `.venv` 里能装、能跑通测试
- [ ] `stats.py` 的三个函数（describe/compare_two/compare_many）有独立单测
- [ ] `run_eval.py --arm` 参数生效，`meta.json` 带 `arm` 字段
- [ ] 审查通过，记录于 review.md

## 7. 待你确认的关键决策

1. **温度统一改为 0**（包括 debate/reflection 隐式走默认值的调用点）——是否认可？
   会让真实 LLM 模式下的输出更确定，但也会让每个 Agent 的回答"更保守/更单一"，
   如果你希望 debate 阶段保留一点温度制造真实分歧（而不是仅靠上下文差异），可以单独给
   debate 的 LLM 调用留一个非零温度，告诉我数值。
2. **种子不做实质接入**，只保留在 config_hash/meta.json 里做实验命名——是否认可？
   （因为目前没有真实随机源，接入种子只是摆设；如果你预期 M4/M6 会引入抽样类机制
   （比如多数投票时的随机打破平局、或者未来温度非零后的采样评测），可以现在就把
   `random.seed(seed)` 真正调用到那些位置的规划提前写进设计，但目前代码里还没有这类逻辑）。
3. **依赖锁定用直接改 `requirements.txt` 为精确版本**，不引入 poetry/pip-tools 等新工具链——是否认可？
