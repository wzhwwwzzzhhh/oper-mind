# M2 — 评测 Harness + 轻量结构化输出（Design 层）

> 里程碑：M2　|　分支：`feat/m2-harness`　|　状态：设计待批准
> 创建日期：2026-07-14
> 关联路线图：`docs/开发路线图与规划.md` → M2
> 依赖：M1 评测数据集（`data/eval/cases.jsonl` 65 条 + `EvalCase` 契约）

---

## 1. 要解决的问题

M1 造好了 65 条带 golden 标注的评测用例，但**没有引擎去跑它们**。M2 要建这台引擎：

给定数据集 + 一个「被测系统配置」，自动地：
1. 逐条把 `query` 喂进 pipeline，跑出诊断报告 + 全链路 trace；
2. 对照 golden 给每条打分；
3. 把逐条结果 + 汇总指标落盘成可复现的实验产出。

这是后续 M4 核心实验（多智能体 vs 单模型基线、各机制消融）的**唯一跑分通道**——所有论文数字都从这台 harness 出。

## 2. 核心约束：mock 模式下的指标分层

读 `src/core/llm.py:61-114` 后确认一个根本事实：mock 模式下 `_mock_chat` 在拿到工具结果后**恒定返回一段 DB 味固定诊断**（全表扫描 / status 索引），与输入域无关。推论：

- **mock 下 pipeline 产出是确定性的** → 适合测 harness 管道本身、适合答辩复现，但不能用 mock LLM 当 judge（它不会真的评估）。
- **真质量分必须切真 LLM** → judge 需要真实推理能力。

因此指标**必须分两层**，harness 要两层都支持：

| 指标层 | 数据来源 | mock 可跑 | 论文用途 |
|---|---|---|---|
| **确定性指标（trace-based）** | 只读 `coordinator.get_trace()` | ✅ 免费、可复现 | 路由正确性、pipeline 完整性、机制触发率 |
| **质量指标（judge-based）** | LM-as-judge 对照 golden | ❌ 需真 LLM（mock 下为 stub） | 根因命中、key_points 覆盖——多智能体核心价值 |

设计原则：**mock 模式下 harness 全管道跑通（确定性指标真算 + judge 出 stub 分），切真 LLM 时自动启用真 judge**。judge 是否为 stub 由 `LLMClient` 是否 mock 决定，harness 不感知细节。

## 3. 模块与接口设计

新增目录 `src/eval/`（评测层代码，与 `data/eval/` 的数据分离）：

```
src/eval/
├── __init__.py
├── metrics.py       # 确定性指标：从 trace 抽取路由/机制/完整性
├── judge.py         # LM-as-judge：对照 golden 打质量分（含 mock stub）
├── runner.py        # harness 主体：加载数据集→驱动 pipeline→打分→落盘
└── result_schema.py # 结果契约（Pydantic）：单条结果 + 汇总
```

> 注：数据契约 `EvalCase` 已在 `data/eval/schema.py`（M1），M2 不动它，只 import。

### 3.1 结果契约（result_schema.py）

```python
class CaseResult(BaseModel):
    case_id: str
    domain: str
    difficulty: str
    # 确定性指标
    routed_strategy: str          # trace 实际路由到的策略
    strategy_hit: bool            # == expected_strategy
    participated_agents: list[str]
    agents_hit: bool              # 参与 agent 覆盖 expected_agents
    debate_triggered: bool
    debate_hit: bool              # == expects_debate
    pipeline_complete: bool       # 是否走完 report+reflection
    # 质量指标（judge）
    root_cause_score: float       # 0-1，golden 根因命中度
    key_points_recall: float      # 0-1，golden_key_points 覆盖率
    judge_is_stub: bool           # 是否 mock stub 分（论文里要标注）
    # 原始产出（留痕）
    report_text: str
    error: str = ""               # 单条异常兜底，不中断整批

class EvalSummary(BaseModel):
    config_hash: str              # 被测配置指纹（复现关键）
    total: int
    strategy_accuracy: float
    agents_accuracy: float
    debate_accuracy: float
    pipeline_complete_rate: float
    mean_root_cause_score: float
    mean_key_points_recall: float
    judge_is_stub: bool           # 整批是否 stub judge
    by_domain: dict[str, dict]    # 分域指标
    by_difficulty: dict[str, dict]
```

### 3.2 确定性指标（metrics.py）

纯函数，输入 `EvalCase` + `trace`（`list[dict]`，来自 `coordinator.get_trace()`），输出确定性字段。不调 LLM。

trace 事件结构已知（读 `src/core/graph.py`）：`{"node": "route"|"direct"|"chain"|"parallel"|"conflict_check"|"debate"|"report"|"reflection", "detail": str}`。

- `routed_strategy`：从 trace 里找 `direct`/`chain`/`parallel` 节点。
- `participated_agents`：direct 看 detail 的目标；chain/parallel 看对应节点。
- `debate_triggered`：trace 是否含 `debate` 节点。
- `pipeline_complete`：是否同时含 `report` 和 `reflection`。

### 3.3 LM-as-judge（judge.py）

```python
class Judge:
    def __init__(self, llm: LLMClient): ...
    def score(self, case: EvalCase, report_text: str) -> tuple[float, float, bool]:
        """返回 (root_cause_score, key_points_recall, is_stub)"""
```

- **真 LLM**：给 judge 一个严格 prompt，让它对照 `golden_root_cause` 判根因命中度（0-1），对照 `golden_key_points` 逐点判是否被报告覆盖（recall）。judge 用 `temperature=0.0`，输出 JSON。
- **mock stub**（`_is_mock(llm)` 为真）：返回确定性占位分（如根因 0.5 / recall = 命中的 key_point 关键词数 / 总数，用简单子串匹配），并置 `is_stub=True`。这样 mock 下管道能跑、数字稳定可复现，但论文里明确标注「stub 分不作质量结论」。

judge 复用 `graph.py` 里的 `_is_mock` 判断（同源，不重复逻辑）。

### 3.4 Runner（runner.py）

```python
def run_eval(cases_path: str, build_system_fn, seed: int = 42) -> EvalSummary:
    """加载数据集→逐条驱动 pipeline→打分→汇总。
    build_system_fn: 无参可调用，返回一个 CoordinatorAgent（复用 src/core/bootstrap.build_system）。
    """
```

流程：
1. `load_cases`（复用 M1 `data/eval/validate.load_cases`）加载 + 结构校验。
2. 固定随机种子（`random.seed(seed)`）——mock_server 用了 `random`，不固定则不可复现。
3. 逐条：`coordinator.route(query)` → 取 `get_trace()` → metrics + judge → `CaseResult`。单条异常进 `error` 字段，不中断整批。
4. 汇总为 `EvalSummary`，落盘到 `experiments/<config_hash>/`（config_hash = 被测配置的稳定指纹）。

**每条都重建 coordinator** 还是复用一个？→ 复用一个（route 是无状态入口，重建成本高）。但记忆系统会跨条累积（`data/memory.json`），这点记入风险，M2 先接受，M4 实验时用「每批清空记忆」保证隔离。

## 4. 落盘与复现

```
experiments/
└── <config_hash>/
    ├── summary.json      # EvalSummary
    ├── cases.jsonl       # 每条 CaseResult
    └── meta.json         # 种子、时间、被测配置、judge 是否 stub、数据集 commit
```

`config_hash`：对「数据集路径 + 种子 + 是否 mock + model 名」做哈希，保证同配置覆盖、异配置分目录。符合规范第 7 节（实验落盘到带 config hash 的目录）。

`experiments/` 加入 `.gitignore`（实验产出不进代码库，只进代码库的是 harness 本身 + 复现脚本）。

## 5. 影响的模块

| 文件 | 变更 |
|---|---|
| `src/eval/__init__.py` | 新建 |
| `src/eval/result_schema.py` | 新建，结果契约 |
| `src/eval/metrics.py` | 新建，确定性指标 |
| `src/eval/judge.py` | 新建，LM-as-judge + stub |
| `src/eval/runner.py` | 新建，harness 主体 |
| `scripts/run_eval.py` | 新建，CLI 入口：`python scripts/run_eval.py [--real]` |
| `.gitignore` | 加 `experiments/` |
| `data/eval/validate.py` | 只读复用 `load_cases`，不改 |

## 6. 结构化契约变化

新增评测层契约 `CaseResult` / `EvalSummary`（`src/eval/result_schema.py`），独立于运行时 `DiagnosisState` 与数据层 `EvalCase`。三者职责分离：
- `EvalCase`（data/eval）= 输入用例；
- `DiagnosisState`（core/graph）= 运行时流转；
- `CaseResult`（src/eval）= 评测产出。

**注意**：design 里提到「轻量结构化输出」原指让 agent 产出结构化诊断（ToolResult/AgentDiagnosis）。评估后决定**M2 先不改 agent 输出**——当前 agent 返回纯文本，judge 用文本对照 golden 已能出分；引入结构化 agent 输出会牵动 graph/report/debate 全链路，风险大且非跑分必需。**降级为：M2 只做评测层结构化（CaseResult），agent 输出结构化推迟到 M6 机制增强**。此决策记入本 design，需你确认。

## 7. 步骤拆分

- `step1-结果契约与确定性指标.md`：result_schema.py + metrics.py + 单测
- `step2-judge与runner.md`：judge.py + runner.py + run_eval.py + mock 全管道冒烟
- `review.md`：里程碑审查（含 mock 跑通证据 + 已知局限）

## 8. 验收标准

- [ ] `python scripts/run_eval.py`（mock）跑通 65 条，产出 summary.json + cases.jsonl + meta.json
- [ ] 确定性指标真算：strategy_accuracy 等有意义（mock 路由确定，应接近满分）
- [ ] judge stub 分稳定可复现（同种子两次跑数字一致）
- [ ] 单条异常不中断整批（人为注入一条坏 case 验证兜底）
- [ ] metrics.py 有独立单测（构造 trace 样例，断言抽取正确）
- [ ] `experiments/` 已 gitignore，不误提交实验产出
- [ ] 审查通过，记录于 review.md

## 9. 待你确认的关键决策

1. **指标分两层**（确定性 trace 指标 + judge 质量分），mock 下 judge 为 stub、真 LLM 下为真 judge——是否认可？
2. **M2 不改 agent 输出结构化**，把 ToolResult/AgentDiagnosis 推迟到 M6——是否认可？（这是对原 roadmap「轻量结构化输出」的降级，理由见 §6）
3. **judge 的评分口径**：根因用 0-1 连续分、key_points 用 recall，是否合适？还是你想要更严格的 rubric（如逐点 0/0.5/1 三档）？
