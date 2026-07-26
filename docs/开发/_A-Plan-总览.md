# A-Plan 总览 — OperMind 全栈 Agent 运维诊断产品

> 创建日期：2026-07-20　|　阶段二调整：2026-07-25
>
> **本文件是项目总进度、当前执行顺序与唯一下一步的唯一真相源。** 阶段二的范围、产品决策和里程碑明细见 `docs/开发/_B-V1产品化开发计划.md`；后者不替代本文件的进度状态。

---

## 1. 产品方向

OperMind 从“多 Agent 运维诊断 Demo”演进为面向运维工程师、SRE 与系统管理员的**全栈 + Agent 运维诊断产品**。

产品主流程：

```text
选择环境或告警事件
→ 创建或进入诊断会话
→ 描述问题
→ Agent 实时诊断
→ 展示根因、证据、影响、置信度、建议与风险
→ 高风险操作进入审批
→ 保存会话、事件与报告，可恢复、追问和审计
```

两个前端职责明确分离：

- `frontend/`：V1 主产品前端，面向运维用户，默认结果优先；完整 Agent 过程按需跳转。
- `report/`：阶段一 M7 产物，面向研发、实验、答辩与调试，展示 Trace、Replay、Debate、Reflection 和实验指标。

## 2. 阶段一：M0–M7 历史完成/冻结

阶段一验证了 Agent Core 与可观察性基础，历史日志和代码继续保留，**不再作为当前产品化主线执行入口**。

| 里程碑 | 状态 | 历史交付 |
|---|---|---|
| M0 | 已完成/冻结 | 环境地基、安全与系统装配治理 |
| M1 | 已完成/冻结 | 评测数据集与 Pydantic 契约 |
| M2 | 已完成/冻结 | 评测 Harness、指标与 Judge |
| M3 | 已完成/冻结 | 可复现性、固定种子与统计能力 |
| M4 | 已完成/冻结 | 真实评测基础设施与可比条件 |
| M5 | 已完成/冻结 | 多 Agent 价值对比与实验结果 |
| M6 | 已完成/冻结 | FastAPI、统一错误体、SSE 与 Trace 契约 |
| M7 | 已完成/冻结 | `report/` 研发/实验/Trace 可观察性前端：同步诊断、回放、SSE 增量和 M5 指标看板 |

M7 原计划中的“联调与视觉收口”不再作为独立产品里程碑继续推进；其稳定演示、报告、产品收口与工程化要求分别纳入 P6、P7。原 M8 的端到端打磨与面试材料也被 P6/P7 吸收。

## 3. 阶段二：P0–P7 当前主线

| 里程碑 | 名称 | 状态 | 目标 |
|---|---|---|---|
| **P0** | **V1 产品化基线** | 已完成 | 产品边界、架构、API v1 契约与主前端原型已收口 |
| **P1** | **应用后端与持久化地基** | 🟡 P1.1b 已完成 | 环境、配置与根资源路径已收口；下一步先设计持久化地基，再进入 SQLAlchemy、Migration、Repository 与 Application Service |
| P2 | 会话诊断闭环 | 待开始 | Session、Run、结构化结果、SSE 持久化与恢复 |
| P3 | 主前端工作台 | 待开始 | `frontend/` 产品外壳、会话与结果优先工作区 |
| P4 | 环境、数据源与知识 | 待开始 | Environment、DataSource、连接器、Runbook 与记忆治理 |
| P5 | 告警、事件与审批闭环 | 待开始 | Alert、Incident、ActionProposal、Approval 与审计 |
| P6 | 报告与产品收口 | 待开始 | 报告、导出、搜索、通知、偏好及 `report/` 高级分析入口 |
| P7 | 测试、部署与生产加固 | 待开始 | 测试矩阵、Agent 回归、安全、CI/CD、部署与演示材料 |

状态图例：已完成/冻结 = 历史基线；🟡 进行中 = 当前里程碑；待开始 = 尚未进入实现。

## 4. 当前唯一下一步

**P1.1c：应用后端地基设计**。

P0 已完成：产品边界、架构盘点、API v1 契约和结果优先的 HTML 原型均已收口；React 工程仍未初始化。P1.1a 已以 `1559266 chore: 恢复P1环境基线` 提交，根 `.venv`、锁定依赖、mock 健康检查、API smoke 与 pipeline 已形成稳定环境基线。

P1.1b 已完成并提交：集中式 `backend/src/project_paths.py` 固定解析仓库根、`backend/`、根 `config/`、`data/` 与 `experiments/`；配置按本地 YAML、模板 YAML、`OPERMIND_*` 覆盖运行，显式 `api_key="mock"` fallback 保持可用。脚本、pytest 与根评测校验不再依赖启动目录，阶段一 `/diagnose`、`/diagnose/stream` 保持兼容。

P1.1b 提交后，唯一下一步为 **P1.1c：应用后端地基设计**：先依据 P0.3 设计 SQLAlchemy/Alembic、SQLite/PostgreSQL 兼容、迁移节奏、Domain/Repository/Application Service 边界与安全降级；不得直接实现数据库、迁移或 `/api/v1` 路由。
## 5. 执行与降级原则

```text
P0 基线与原型
→ P1 持久化地基
→ P2/P3 会话诊断纵向切片（交错推进）
→ P4 数据源与知识
→ P5 告警、事件与审批
→ P6 报告与产品收口
→ P7 测试、部署与生产加固
```

- 采用纵向切片：产品流程 → 数据模型 → API → Agent 接入 → 前端 → 最小验证 → Review → Commit。
- Agent Core 不推倒重来。产品会话、持久化、事务、权限和审计放在 Application Service / Repository 边界，Agent 节点专注诊断推理。
- 产品 API 向 `/api/v1` 统一演进；`backend/src/api/` 是当前 HTTP/SSE 契约边界。
- 真实数据库、数据源与前后端联调必须先共同确认目标、权限、数据、契约、回退和验收场景；`api_key="mock"` 与确定性 mock fallback 始终可用。
- 历史路线图 `docs/开发路线图与规划.md`、历史开发日志和 `docs/初始开发/` 不删除；它们不定义当前下一步。

## 6. 开发日志与分支

- 阶段一历史日志继续在 `docs/开发/M<N>-<名称>/`；阶段二日志在 `docs/开发/P<N>-<名称>/`。
- 重要 Step 按 `Design → Step → Code → Test → Review → Commit` 闭环，必要时使用当前里程碑的 `HANDOFF.md` 交接。
- 阶段二里程碑使用 `feat/pN-*` 分支，提交必须显式暂存目标文件，禁止无检查的 `git add .`。
