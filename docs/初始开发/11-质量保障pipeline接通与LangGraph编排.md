# 11 质量保障 pipeline 接通与 LangGraph 编排

> 本文档记录一次核心改造:把当前"路由 → 单 Agent → 返回"的断裂链路,重建成一张
> LangGraph 编排图,串起 **LLM 路由 → 领域 Agent(并发) → Debate → Report → Reflection**
> 的完整多智能体协作闭环。这是论文核心贡献(三种协作模式对比 + Debate/Reflection 有效性)
> 得以做实验的前提,也是秋招 demo 的主线。

---

## 一、改造动机(为什么现在必须做这个)

对现有代码做了一轮盘点,结论是**"骨架有、神经断"**:

| 模块 | 文档规划 | 代码实际 | 状态 |
| --- | --- | --- | --- |
| Coordinator 路由 | LLM 动态决策直达/链式/并行 | `_decide_strategy` 是**关键词硬匹配**,LLM prompt 写了没调用 | ⚠️ 核心卖点缩水 |
| Debate 辩论 | 并行模式意见分歧时触发 | 类写好,`build_system()` 里 new 了但**返回值被 `_` 丢弃**,从不调用 | ❌ 孤儿 |
| Reflection 复审 | 每份报告生成后必做 | 同上,构造后未被任何地方调用 | ❌ 孤儿 |
| Report Agent | 结构化报告 | chain/parallel 是**手工拼 markdown**,没走 `ReportAgent` | ❌ 孤儿 |
| 并行执行 | "同时分发" | `_route_parallel` 是 **for 循环串行** | ⚠️ 名不副实 |
| LangGraph | 技术栈主打图编排 | `agent_langgraph.py` 是**独立的、只做 DB 的 demo**,主系统仍是手搓 ReAct | ⚠️ 双轨分裂 |

已经接通、本次不动的部分:短期/长期记忆(`ShortTermMemory`/`LongTermMemory`,已在 `BaseAgent` 内使用)、
工具执行层的审批闸门(`ToolRegistry.execute_tool` 已调用 `approval` 检查)。

**当前真实链路**只是:`route(关键词) → 单个 Agent 跑 ReAct → 返回`,后面三层质量保障全是摆设。
所以第一优先级不是加新功能,而是**把 pipeline 接通**,否则实验无从谈起。

---

## 二、架构决策:混合模式

> 主编排用 LangGraph,领域 Agent 内部保留手搓 ReAct。

理由(兼顾毕设与秋招):

- **面试故事最强**:"先手写 ReAct 引擎搞懂底层,再用 LangGraph 做多 Agent 编排"——同时证明底层深度与框架广度。
- **LangGraph 主编排解锁高价值能力**:状态检查点、断点续跑、流式输出、human-in-the-loop 审批、图可视化,写进论文自洽。
- **不浪费现有代码**:三个领域 Agent 内部的 `BaseAgent.run()` ReAct 循环保留,作为图节点被调用。
- `agent_langgraph.py`(独立 DB demo)退出主路径,消除双轨分裂。

配套已定的方向:
- **数据源**:目标全面接真实数据(MySQL/psutil/日志);为保证对比实验可复现,后续配套**故障注入脚本**。本步先用现有 mock 兜底,不阻塞。
- **记忆/规划**等优化点(向量库 RAG、Plan-Execute)按 `10-项目迭代待办清单.md` 排期,本步不动。

---

## 三、目标链路(状态机)

```
START
  └─→ route_node            LLM 决策 strategy(direct/chain/parallel)+ target
         │  条件边(按 strategy)
         ├─→ direct_node     调目标 Agent.run()
         ├─→ chain_node      Server → DB → Log 逐层,后层带上前层结论
         └─→ parallel_node   ThreadPoolExecutor 真并发调多个 Agent
                                   │
                                   └─→ conflict_check_node   结论是否分歧?
                                          │ 条件边
                                          ├─(分歧)→ debate_node   DebateArena 裁决
                                          └─(一致)─────────────┐
         direct/chain 直接汇入 ────────────────────────────────┤
                                                                ▼
                                                          report_node        ReportAgent 出初稿;
                                                                │            若带 review_feedback 则据反馈修订
                                                                ▼
                                                          reflection_node    ReflectionEngine 复审
                                                                │ 条件边
                                          (有问题且 revision_count<2)│           │(通过 / 超上限)
                                                     └──回 report_node──┘        ▼
                                                                               END(final_report)
```

---

## 四、状态定义 DiagnosisState

LangGraph 在节点间传递的状态(TypedDict):

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `query` | str | 用户原始问题 |
| `strategy` | str | 路由策略 direct/chain/parallel |
| `target` | str | direct 模式命中的目标 Agent |
| `agent_results` | dict[str,str] | {agent 名: 诊断结论} |
| `agent_thinking` | dict[str,list] | {agent 名: 思考链路},给可视化用 |
| `has_conflict` | bool | 并行结论是否分歧 |
| `debate_result` | str | 辩论共识 |
| `report_draft` | str | 报告初稿 |
| `review_feedback` | list[str] | Reflection 复审反馈 |
| `final_report` | str | 终稿 |
| `revision_count` | int | 复审回退次数(防死循环) |
| `trace` | list[dict] | 全链路事件流,为前端 SSE + ECharts 铺路 |

---

## 五、文件改动清单

### 新增 `src/core/graph.py` —— 编排图核心
- `DiagnosisState`(见上)
- 节点函数:`route_node` / `direct_node` / `chain_node` / `parallel_node` /
  `conflict_check_node` / `debate_node` / `report_node` / `reflection_node`
- `build_diagnosis_graph(llm, agents, debate, reflection, report) -> CompiledGraph`

### 改动 `src/core/coordinator.py`
- `CoordinatorAgent` 变成图的持有者:`__init__` 编译图,`register_agent` 不变;
  `route(query)` 改为 `graph.invoke(initial_state)` 返回 `final_report`;新增 `get_trace()`。
- 关键词决策逻辑不删除,下沉为 `route_node` 的**兜底**(见设计点)。对外接口保持兼容 main/app。

### 改动 `src/main.py` / `src/app.py`
- `build_system()` 把 `debate/reflection/report` **注入 coordinator**(不再丢弃)。
- `/diagnose` 返回终稿;`show_thinking=True` 时附 `trace`。

### 小修
- `ReportAgent.generate()` 支持"带反馈修订"入参(reflection 回退用)。
- `DebateArena` / `ReflectionEngine` 增加 mock/降级回退,保证无 LLM 也能跑通链路。

---

## 六、关键设计点

1. **LLM 路由 + 关键词兜底**:`route_node` 优先让 LLM 输出 JSON `{strategy, target}`;
   解析失败或 mock 模式则回退到现有关键词规则。既坐实"动态路由"卖点,又保证离线/mock 可测。
2. **真并发**:`parallel_node` 用 `ThreadPoolExecutor`(`BaseAgent.run` 是同步的)。
3. **防死循环**:`reflection_node → report_node` 回退设 `revision_count < 2` 上限。
4. **trace 字段**:每个节点向 `trace` 写事件,为后续前端链路可视化铺路(迭代方向)。
5. **降级友好**:Debate/Reflection 在 LLM 不可用/mock 时给出确定性回退,链路不断。

---

## 七、验证方式

- mock 模式(`api_key="mock"`)端到端跑通 **direct / chain / parallel** 三条路径,
  断言 `final_report` 非空、且 debate/reflection 节点确实执行。
- 用 `data/test_cases.json` 的 SQL 跑 direct 路径。
- 真实 DeepSeek 冒烟一次(可选)。

---

## 八、暂不做(留待后续迭代)

- 记忆升级(Chroma 向量库 RAG)、Plan-Execute-Replan —— 见 `10-项目迭代待办清单.md`。
- **真实数据接入(MySQL/psutil/日志)+ 故障注入脚本** —— 紧接着的下一步。
- human-in-the-loop 审批:现 `approval.request_approval` 用阻塞 `input()`,在 FastAPI 下会挂起,
  留待用 LangGraph `interrupt` 重做。
- `log_tools.py` 与 `data/mock_logs.py` 的 schema 漂移清理(`rows` vs `rows_examined`、list vs dict)。

---

## 九、⚠️ 安全待办(非代码)

`config/config.local.yaml` 提交了一个**真实 DeepSeek API Key**。建议:
- 确认该文件在 `.gitignore` 中;
- 若已进入 git 历史,轮换该 key。

---

> 完成后即拥有一条**可运行、可演示、可做对比实验**的完整多智能体协作链,
> 支撑论文第五章实验与秋招 demo。
