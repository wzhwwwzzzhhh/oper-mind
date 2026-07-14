# M1 — 评测数据集建设（Design 层）

> 里程碑：M1　|　分支：`feat/m1-dataset`　|　状态：进行中
> 创建日期：2026-07-14
> 关联路线图：`docs/开发路线图与规划.md` → M1

---

## 1. 要解决的问题

论文核心卖点是「多智能体协作」相对单模型基线的价值，这需要**统计显著性**支撑。当前评测资产撑不起结论：

1. **样本量不足**：`data/test_cases.json` 只有 7 条，且全是 DB/SQL 单领域。7 条无法做 Wilcoxon / Friedman 检验，也覆盖不到多智能体真正拉开差距的场景。
2. **缺跨领域复合故障**：多智能体的价值恰恰在 chain（逐层排查）与 parallel（冲突辩论）场景，现有用例一条都没有。
3. **schema 扁平且强耦合**：现有字段 `sql/category/expected_diagnosis/expected_tools` 只能描述 SQL 单例，无法表达「期望路由策略」「期望参与 Agent」「难度分级」「golden 根因」等评测必需维度。
4. **无 golden 标注结构**：M2 的 LM-as-judge 需要每条用例有可对照的期望根因/关键结论，现有 `expected_diagnosis` 是一句话，粒度不够。

目标：扩到 **50–100 条**结构化用例，覆盖 db/server/log 单领域 + 跨领域复合，含 golden 标注，为 M2 评测 harness 和 M4 主实验提供地基。

## 2. 关键约束（来自现有实现，必须遵守）

设计 schema 前先摸清了 `src/core/graph.py` 的路由契约，用例必须与之对齐，否则 mock 冒烟会路由错：

1. **策略取值**：`direct` / `chain` / `parallel`（`DiagnosisState.strategy`）。
2. **direct 目标 Agent**：`db` / `server` / `log`（注册名，见 `bootstrap.build_system`）。
3. **mock 模式走关键词兜底路由**（`_keyword_strategy` / `_keyword_target`），不是 LLM。所以用例的自然语言 `query` **必须含能命中目标策略/Agent 的关键词**，否则 mock 下路由错误：
   - `db` 关键词：select/from/where/join/explain/sql/索引/慢查询/慢sql
   - `server` 关键词：cpu/内存/磁盘/进程/负载/服务器/线程/network/网络
   - `log` 关键词：日志/错误/异常/报错/log/timeout/超时
   - `parallel` 关键词：体检/全面/整体/健康/大促/巡检/上线前
   - `chain` 关键词：很慢/卡/故障/排查/定位/慢/不稳定；或命中 ≥2 个领域关键词
4. **chain 固定顺序** server→db→log；**parallel** 跑全部已注册 Agent 后过 `conflict_check`。
5. **mock 分歧检测是启发式**：并行结论前 60 字不同即判为分歧 → 触发 debate。用例若想覆盖 debate 分支，需保证多 Agent 结论文本有差异。

## 3. 方案与取舍

### 3.1 数据 schema（Pydantic 定契约）

新建 `data/eval/schema.py`，用 Pydantic 模型定死用例结构，替代扁平 dict：

```
EvalCase:
  case_id: str            # 稳定 ID，如 "db-001"、"chain-003"
  query: str              # 用户自然语言问题（含关键词，保证 mock 可路由）
  domain: Literal["db","server","log","compound"]  # 领域标签
  expected_strategy: Literal["direct","chain","parallel"]  # 期望路由
  expected_agents: list[str]   # 期望参与的 Agent（direct=1个，chain/parallel=多个）
  difficulty: Literal["easy","medium","hard"]  # 难度分级
  golden_root_cause: str       # golden 根因（供 LM-as-judge 对照）
  golden_key_points: list[str] # 期望命中的关键结论点（评分要点）
  expects_debate: bool         # 是否期望触发辩论（仅 parallel 可能为 true）
  source: Literal["seed","synthetic"]  # 来源：迁移自旧用例 / 新造
  notes: str = ""              # 备注（如注入的 mock 现象说明）
```

**取舍**：
- 用 `case_id` 字符串而非旧的整数 `id`，便于按领域分段（db-*/server-*/log-*/chain-*/parallel-*）。
- 不在 schema 里塞 `expected_tools`（旧字段）——工具命中是 DB Agent 内部行为，评测层关注的是「根因是否命中」，工具留作 M2 可选的过程指标，避免 schema 过早绑死。
- `golden_key_points` 用列表而非长文本，让 LM-as-judge 能逐点计分（M2 用）。

### 3.2 数据存储格式

- 用例存 `data/eval/cases.jsonl`（每行一条 JSON），而非单个大 JSON 数组。
  - 取舍：JSONL 便于增量追加、diff 友好、逐行校验；50–100 条规模下比大数组好维护。
- schema 校验脚本 `data/eval/validate.py`：加载 JSONL → 逐条过 Pydantic → 报告非法条目 + 领域/策略/难度分布统计。

### 3.3 用例分布（草稿版目标 ≈ 60 条）

| 领域/策略 | 条数 | 说明 |
|---|---|---|
| db（direct） | 15 | 迁移旧 7 条 + 扩 8 条（索引/排序/JOIN/函数失效/复合索引/高危） |
| server（direct） | 10 | CPU/内存/磁盘/进程/负载 |
| log（direct） | 10 | 错误检索/慢查询日志/OOM/连接池 |
| chain（compound） | 12 | 模糊卡慢 → server→db→log 逐层，跨领域因果链 |
| parallel（compound） | 13 | 全面体检；其中 ≥5 条构造多 Agent 结论分歧以触发 debate |

**取舍**：先造 ≈60 条草稿（够跑通 harness + 初步统计），M2 验证评分管线后如需更强统计功效再扩到 100。符合「先跑起来再迭代」。

### 3.4 golden 标注策略

- **草稿自动生成 + 人工抽查**（用户已确认走这条路）：我按注入的 mock 现象和领域知识生成 `golden_root_cause` / `golden_key_points` 初版，用户后续抽查修订。
- 每条 `notes` 记录该用例依赖的 mock 现象，便于抽查时对照。

## 4. 影响的模块

| 文件 | 变更 |
|---|---|
| `data/eval/schema.py` | 新建，Pydantic 用例模型 |
| `data/eval/cases.jsonl` | 新建，≈60 条草稿用例 |
| `data/eval/validate.py` | 新建，schema 校验 + 分布统计脚本 |
| `data/test_cases.json` | 保留（旧 7 条，被迁移进 cases.jsonl，不删以免破坏 tests/test_diagnosis.py） |

## 5. 结构化契约变化

新增评测层契约 `EvalCase`（Pydantic）。这是评测资产的契约，独立于诊断链路的 `DiagnosisState`，不影响运行时链路。

## 6. 步骤拆分

- `step1-schema与校验脚本.md`：定义 Pydantic schema + validate.py
- `step2-生成草稿用例.md`：生成 ≈60 条 cases.jsonl（可派 agent 按领域并行造）
- `step3-校验与分布统计.md`：跑 validate.py，确认分布达标、全部合法
- `review.md`：里程碑级审查

## 7. 验收标准

- [ ] `data/eval/schema.py` 定义 `EvalCase`，字段类型标注齐全
- [ ] `data/eval/cases.jsonl` ≥ 50 条，覆盖 db/server/log/chain/parallel
- [ ] 每条用例的 `query` 关键词能在 mock 模式命中其 `expected_strategy`
- [ ] `data/eval/validate.py` 跑通：全部条目合法，打印分布统计
- [ ] parallel 用例中 ≥5 条 `expects_debate=true`
- [ ] 审查通过，记录于 `review.md`
