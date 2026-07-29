# OperMind V1 产品化开发计划（阶段二）

> 创建日期：2026-07-25
> 状态：草案已收敛，后续边开发边校准
> 适用目录：`D:\market-handsome\oper-mind`
> 进度真相源仍为：`docs/开发/_A-Plan-总览.md`

## 1. 阶段定义

### 阶段一：Agent 核心与能力验证（M0–M7）

已基本完成：LangGraph 工作流、direct/chain/parallel 路由、多专业 Agent、Debate、Reflection、审批门基础、记忆、Trace、SSE、FastAPI 契约、实验评测与可观察性前端。

阶段结论：OperMind 的多 Agent 运维诊断核心能够运行，但当前仍偏 Demo，尚未形成可长期使用的产品闭环。

### 阶段二：OperMind V1 全栈产品化（P0–P7）

目标：将 OperMind 从“多 Agent 运维诊断 Demo”发展为具备会话、持久化诊断、环境与数据源、告警事件、审批、知识记忆和报告能力的完整全栈 Agent 应用。

产品名称暂定：**OperMind AI 运维诊断工作台**。

## 2. 已确认的核心决策

1. **个人轻量优先**：V1 面向个人用户的日常运维使用，不以企业级多人协作、组织、共享空间或复杂 RBAC 为前提。
2. **长期多轮会话优先**：一个用户拥有多个长期会话；会话与 Message 是用户主对象。`DiagnosisRun`/RunEvent/SSE 是按需出现的 Investigation 执行细节，不应成为默认用户心智模型。
3. **三类入口汇聚会话**：用户主动提问、真实监控发现、已接入告警未来都必须创建或进入同一会话上下文，不能分别长成聊天页、监控大盘和告警页三个孤岛。
4. **Agent 过程渐进披露**：默认显示可理解的调查概要、发现和证据；展开后显示安全细节；完整 Trace 继续受控进入 `report/`。
5. **处理必须受控**：发现、分析和建议可自动；真实处理必须有 ActionProposal、明确授权、最小权限、审计和验证。当前未实现时只显示诚实边界。
6. **保留两个前端但职责分离**：`frontend/` 是个人 AI 运维助手主产品；`report/` 是研发、调试、实验、答辩的 Trace/Replay 前端，不能改作主产品。
7. **Agent Core 不推倒重来**：现有 Agent 编排是调查执行基础，后续在 Application Service/API 层补产品语义和安全边界。
8. **继续纵向切片**：产品流程 → 数据模型 → API → Agent 接入 → 前端 → 最小验证 → Review → Commit；不采用后端和前端割裂的大批量开发。
9. **结构化契约优先**：正式产品不能只依赖 Markdown 和前端正则解析；结论、证据、影响、风险和建议必须有稳定结构化事实。

当前产品体验设计真相源为 `docs/开发/治理-个人AI运维助手产品重定位/`。P0 原型与 P3.1–P3.4c 的布局、导航、工作台叙事仅保留为历史/技术基线，不再直接定义新体验；既有 `/api/v1` 契约、P2 行为和测试仍必须继承。

## 3. 产品主流程

```text
主动提问 / 真实监控发现 / 已接入告警
→ 创建或进入个人长期会话
→ 用户和 AI 多轮沟通
→ 按需创建 Investigation（内部由 DiagnosisRun 承载）
→ 会话内展示判断、影响、证据、不确定性和安全建议
→ 持续追问，或在未来对处理提议明确授权
→ 处理后验证并留下可恢复记录
```

V1 的第一验证场景是**用户主动发起的连续诊断对话**：用户无需理解 Run、SSE、Agent 或 Trace，仍能完成提问、理解调查进度、获得证据化结论并继续追问。监控/告警是同一主线的后续入口，不得在无真实数据条件下伪造。

## 4. 系统边界

```text
React 主前端
  → FastAPI /api/v1 应用 API
    → Application Services
      ├── 会话与诊断
      ├── 环境与数据源
      ├── 告警与事件
      ├── 审批
      ├── 知识与记忆
      └── 报告
    → Agent Orchestration Core
      ├── LangGraph
      ├── 专业 Agent / Tool
      ├── Debate / Reflection / Approval
      ├── Memory
      └── Trace
    → Repository / Database

report/ ← Trace、Replay、实验指标与研发可观察性
```

禁止把业务持久化、会话管理和产品权限继续直接塞进 Agent 节点；Agent Core 负责诊断推理，Application Service 负责产品用例与事务编排。

## 5. 目录结构约束

目标根目录保持清晰，不再随功能随意新增顶层目录：

```text
oper-mind/
├── backend/       # FastAPI、应用服务、Agent Core、持久化、测试和脚本
├── frontend/      # V1 主产品 React 前端
├── report/        # 原 M7 可观察性/实验前端
├── config/        # 配置模板
├── data/          # 本地数据与确定性 mock
├── docs/          # 规划、架构、产品和开发日志
├── experiments/   # 评测与实验产物
├── AGENTS.md
└── CLAUDE.md
```

后端内部目标分层（P0/P1 再结合现有代码确认，禁止一次性大搬家）：

```text
backend/src/
├── api/           # HTTP/SSE 契约与路由
├── application/   # 产品用例服务
├── domain/        # 产品实体与领域规则
├── infrastructure/# ORM、Repository、连接器实现
├── agents/        # 专业 Agent
├── core/          # Agent 编排核心
├── tools/         # Agent 工具
├── memory/        # Agent 记忆
└── app.py
```

原则：先定义边界，再在纵向切片中渐进迁移；不为“目录看起来漂亮”进行无业务收益的大重构。

## 6. V1 数据模型候选

数据模型按用户可见语义与内部执行语义分层；不要求一次实现全部：

- `Session`：个人长期会话（产品上可称 Conversation）；
- `Message`：用户、助手或系统提醒消息；
- `DiagnosisRun`：一次 Investigation 的可追踪内部执行；
- `RunEvent`：持久化的调查进度/SSE 事件；
- `DiagnosisResult`：结构化发现、证据、影响、建议、风险与审批需求；
- `Environment` / `DataSource`：后续独立监控与调查的受控连接目标；
- `Monitor` / `Finding`：未来的真实监控对象与异常发现，当前不创建假资源；
- `Alert`：后续接入的告警来源；
- `ActionProposal` / `Approval` / `ActionExecution`：受控处理、授权、审计与验证；
- `Report`：诊断/处理报告及导出记录；
- `KnowledgeDocument` / `MemoryRecord`：受控的 Runbook、架构说明和长期记忆。

核心关系应是：`Session → Message → Investigation(DiagnosisRun) → DiagnosisResult/RunEvent`；Alert、Monitor 和 Action 未来只能通过可恢复、可审计关联进入该会话，而不能依靠前端临时拼接。

## 7. API 基线

P0 统一：

- `/api/v1` 前缀；
- ID、UTC 时间、分页、错误体、request/trace ID；
- SSE 事件名、事件 ID、断线恢复和最终状态；
- OpenAPI 与前端 TypeScript 类型边界；
- 结构化 DiagnosisResult 契约。

第一个诊断闭环建议接口：

```text
POST   /api/v1/sessions
GET    /api/v1/sessions
GET    /api/v1/sessions/{session_id}
PATCH  /api/v1/sessions/{session_id}
DELETE /api/v1/sessions/{session_id}
GET    /api/v1/sessions/{session_id}/messages
POST   /api/v1/sessions/{session_id}/runs
GET    /api/v1/runs/{run_id}
GET    /api/v1/runs/{run_id}/events
GET    /api/v1/runs/{run_id}/stream
```

执行语义：先 POST 创建 `DiagnosisRun` 并返回 `run_id`，再按 `run_id` 订阅 SSE；事件和最终结果持续持久化，页面刷新后可恢复。

结构化结果至少包含：

```text
summary, severity, confidence, root_causes, evidence,
impact, recommendations, risks, requires_approval, agent_summary
```

Markdown 可作为展示补充，但不能作为唯一业务契约。

## 8. 主前端信息架构

```text
主导航（目标信息架构，非当前路由实现）
├── 会话：历史会话、新建、消息流、调查卡、持续追问
├── 监控：关注对象、健康概览、异常发现（P4 后才可出现）
├── 提醒与告警：进入或创建关联会话（P5 后才可出现）
├── 处理记录：提议、授权、执行和验证（后续能力）
└── 设置与连接：数据源、个人偏好、模型与安全边界（分步进入）
```

会话内固定信息层级：

1. 默认显示助手回答：当前判断、影响/不确定性、证据、建议和继续追问；
2. 按需显示 Investigation 摘要：调查状态、已发现、下一步、是否需要用户输入；
3. 展开显示安全的步骤摘要、耗时、关联 ID；完整 Trace 受控跳转 `report/`。

当前没有真实监控、Alert、Action 或多人协作时，对应入口只能是诚实空状态或根本不展示；不得用静态假数据冒充已接通的能力。

## 9. 产品化里程碑

### P0：产品化基线收敛（已完成，体验原型已归档）

- 固化早期产品边界、API v1 草案、分层和旧主前端原型；
- P0 原型仍可说明当时的 Result/Trace 边界，但不再定义 R1 的会话体验。

### P1：应用后端与持久化地基（已完成）

- SQLAlchemy 2、Alembic、Repository、Application Service、统一异常和配置；
- ID、UTC 时间、请求追踪和 Migration 基线。

### P2：会话诊断闭环（已完成）

- Session、Message、DiagnosisRun、RunEvent、DiagnosisResult；
- 幂等受理、SSE、成功/失败状态、刷新恢复和结构化结果；
- 是会话优先体验的可信技术基础，但不是最终用户体验定义。

### P3：个人会话主体验

- P3.1–P3.4c：已建立 React 工程、v1 client/Mock、恢复读模型、Run 受理、SSE 和 Result 技术基线；
- P3.5：个人会话主体验与 API 差距 Design；
- P3.6：仅在 P3.5 获批后，做会话优先的最小前端/Mock 纵向切片；
- 始终保留错误、空状态、断线恢复和 `report/` 受控边界，不伪造平台能力。

### P4：独立监控、环境、数据源与知识

- 先定义独立监控对象、连接条件、最小权限、健康检查和诚实空状态；
- 再逐项接入日志、指标、DB、Redis、Docker、K8s 等真实或明确声明的确定性数据源；
- 定义异常发现如何进入会话，不提前建设假大盘。

### P5：提醒/告警进入会话与受控处理

- Alert → Conversation → Investigation → 建议 → ActionProposal → 明确授权 → 审计 → 验证；
- 个人 V1 不引入多人 Incident 协作；是否需要 Incident 资源留待该阶段基于真实使用场景再决定；
- 将现有审批门演进为正式且可审计的产品能力。

### P6：个人产品收口

- 处理验证、会话/报告搜索、标签、归档、导出、通知和个人偏好；
- 与 `report/` 的高级研发分析入口保持受控打通。

### P7：测试、部署与生产加固

- Service/API/Repository/前端组件/E2E 测试；
- Agent 回归、并发、超时、SSE 重连；
- 安全、权限、Docker、CI/CD、部署文档。

## 10. 每个切片的固定工作流

```text
Design → Step → Code → Minimum Test → Review → Commit
```

每个 step 必须能在一个上下文内闭环；预计超过 3–5 个实现文件、跨上下文或出现重要审查问题时，先更新当前里程碑 `HANDOFF.md`。不把多个后续步骤混在一次提交。

## 11. 执行入口（不维护独立“唯一下一步”）

- 项目状态、执行顺序和当前唯一下一步只看 `docs/开发/_A-Plan-总览.md`。
- 当前产品体验设计入口是 `docs/开发/治理-个人AI运维助手产品重定位/`；R1/P3.5 已于 2026-07-29 提交为 `6b0290b`，P3.6a 必须另获用户明确实现授权。
- P3.1–P3.4c 工作台的布局、导航和旧“下一步”是历史/技术基线；既有 `/api/v1` 契约、P2 行为和测试事实继续继承，但不能直接定义新体验。
- 文档分类、当前交接和恢复顺序见 `docs/开发/README.md`。影响阶段二范围时先修订本计划，再同步 A-Plan 的状态与唯一下一步；不得反向在本文件维护第二个进度入口。
