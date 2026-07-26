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

1. **Web 优先**：主前端使用 React + TypeScript；未来确有本机能力需求时再用 Tauri 封装桌面端。
2. **保留两个前端但职责分离**：
   - `frontend/`：面向运维/SRE 用户的主产品前端；
   - `report/`：原 M7 前端，面向开发、调试、实验、答辩，展示 Trace、Replay、Debate、Reflection 和 M5 指标。
3. **Agent Core 不推倒重来**：现有 Agent 编排是产品核心，后续以边界清理和专项优化为主。
4. **改用纵向切片开发**：产品流程 → 数据模型 → API → Agent 接入 → 前端 → 最小验证 → Review → Commit；不采用“后端全部写完再统一写前端”。
5. **测试暂时不是主线，但保留最小质量门**：启动检查、Migration、核心 API smoke、SSE 联调、前端构建和主流程人工验收必须保留；完整测试体系后置到 P7。
6. **结构化契约优先**：正式产品不能只依赖 Markdown 和前端正则解析，诊断结果必须有稳定的结构化字段。
7. **主产品结果优先、过程按需展开**：主前端默认展示根因、证据、影响、置信度、建议、风险和审批；Agent 内部完整过程跳转 `report/` 查看。

## 3. 产品主流程

```text
选择环境或告警事件
→ 创建/进入诊断会话
→ 描述问题
→ Agent 实时诊断
→ 展示根因、证据、影响、置信度和建议
→ 高风险操作进入审批
→ 保存事件、会话和报告
→ 后续可恢复、追问和审计
```

V1 用户优先面向：运维工程师、SRE、系统管理员、运维负责人。暂不在早期引入复杂 RBAC。

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

P0 需要先定义关系和生命周期，不要求一次实现全部：

- `Session`：诊断会话；
- `Message`：用户/助手/系统消息；
- `DiagnosisRun`：一次可追踪的诊断执行；
- `RunEvent`：持久化的 SSE/Trace 事件；
- `DiagnosisResult`：结构化诊断结果；
- `Environment`：生产/测试/开发等目标环境；
- `DataSource`：日志、指标、DB、Redis、Docker、K8s 等连接配置；
- `Alert`：外部或手动录入的告警；
- `Incident`：承载完整处置生命周期的事件；
- `Approval` / `ActionProposal`：高风险操作建议与审批；
- `Report`：诊断/事件报告及导出记录；
- `KnowledgeDocument`：Runbook、架构说明等知识；
- `MemoryRecord`：可审计的长期记忆记录。

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
核心
├── 工作台
├── 诊断会话
└── 告警事件

资源
├── 环境与数据源
├── 知识与记忆
└── Agent 能力

治理
├── 审批记录
├── 报告中心
└── 系统设置
```

顶部仅保留：当前环境、Mock/Real、模型状态、通知和用户。

诊断工作区建议按场景使用三栏：左侧会话/事件上下文，中间问题与诊断结果，右侧环境、关键证据、风险、审批和协作摘要；不是所有页面永久三栏。

Agent 展示分三级：

1. 默认进度摘要；
2. 可展开的 Agent 状态、耗时、发现、冲突、Debate/Reflection 摘要；
3. 跳转 `report/` 查看完整 Trace 和指标。

## 9. 产品化里程碑

### P0：产品化基线收敛

- 固化定位、用户、核心流程、信息架构和两个前端边界；
- 盘点现有后端与接口；
- 形成数据模型关系图和状态机；
- 形成 API v1 草案与结构化结果契约；
- 定义后端分层和目录迁移原则；
- 重做主前端高保真 HTML 原型；
- 用户确认原型后才搭建 React 主工程。

### P1：应用后端与持久化地基

- SQLAlchemy 2、Alembic；
- SQLite 本地开发，保持 PostgreSQL 兼容；
- Repository、Application Service、统一异常和配置；
- ID、时间戳、请求追踪和 Migration 基线。

### P2：会话诊断闭环（第一个纵向切片）

- Session、Message、DiagnosisRun、RunEvent、DiagnosisResult；
- 创建会话与运行、SSE、同步/失败状态、结果持久化；
- 刷新恢复、继续追问和历史查看；
- Agent 协作摘要和完整 Trace 跳转。

### P3：主前端工作台

- React + TS + Vite、React Router、TanStack Query、Zustand、Ant Design；
- 产品外壳、工作台、会话列表、诊断工作区；
- 结构化结果卡片、错误/空/断线状态；
- 未实现模块使用诚实空状态，不伪造平台能力。

> P2/P3 按纵向切片交错推进，不是严格串行。

### P4：环境、数据源与知识

- Environment / DataSource 管理；
- Connector 统一接口与健康检查；
- 日志、Prometheus、DB、Redis、Docker、K8s 等逐项接入；
- Runbook、架构说明、历史事件和记忆治理。

### P5：告警、事件与审批闭环

- Alert、Incident、ActionProposal、Approval；
- 告警 → 事件 → 会话 → 诊断 → 建议 → 审批 → 审计 → 关闭；
- 将现有审批门升级为正式产品能力。

### P6：报告与产品收口

- 诊断/事件报告、搜索、标签、收藏、归档；
- Markdown/PDF 导出；
- 通知、用户偏好、工作台统计；
- 与 `report/` 的高级分析入口打通。

### P7：测试、部署与生产加固

- Service/API/Repository/前端组件/E2E 测试；
- Agent 评估回归、并发、超时、SSE 重连；
- 安全、权限、Docker、CI/CD、部署文档。

## 10. 每个切片的固定工作流

```text
Design → Step → Code → Minimum Test → Review → Commit
```

每个 step 必须能在一个上下文内闭环；预计超过 3–5 个实现文件、跨上下文或出现重要审查问题时，先更新当前里程碑 `HANDOFF.md`。不把多个后续步骤混在一次提交。

## 11. 当前唯一下一步

**P1.1a：环境基线恢复**。P0 的规划边界、架构盘点、API v1 契约和 HTML 原型已完成；本 Step 只恢复可重复后端环境，不直接实现持久化功能：

1. 确认可用 Python 3.10+、当前 `.venv`、后端依赖和仓库根导入路径；
2. 在用户授权后以当前仓库根 `.venv` 重建环境并安装 `backend/requirements.txt`；
3. 用 mock 配置验证 Python、依赖导入、健康检查、`backend/tests` 最小 smoke 和 direct / chain / parallel pipeline；
4. 如实记录命令、结果、失败原因和环境限制，不为通过验证修改业务逻辑；
5. 独立 Review 后以文档提交收口。

P1.1a 完成后进入 P1.1b 的配置/数据路径收口。P1 后续的 ORM、Migration、Repository 和新路由必须遵循 P0.3 契约；旧 `/diagnose`、`/diagnose/stream` 必须保持兼容。

本计划是方向基线，不是不可修改的瀑布计划；边做边优化，但任何范围变化必须回写本文件和 `_A-Plan-总览.md`，避免口头决策漂移。
