# PRD 索引（docs/prd/）

> 本目录是**需求唯一事实来源**。执行 AI 围绕这里的 PRD 干活，Claude（PM）按 PRD 在大阶段验收。
> 写作规范见 `项目根/.claude/skills/prd-writing/SKILL.md`。
> 产品事实只以 `docs/产品定义.md`、`docs/路线图.md`、`docs/开发规范.md` 为准。

## 需求立项顺序与角色边界

新增阶段或能力统一从本目录的 PRD 开始：

```text
路线图候选
→ PRD 草案
→ 用户确认 PRD
→ 创建唯一 GitHub Issue
→ 实施 Design
→ 独立 Review
→ 用户确认实施 Design
→ active Workpack / 独立 worktree
→ 实现、测试、Review、PR 与归档
```

- 一个正式实施阶段默认只有一个 PRD、一个 Issue 和一个 active Workpack；Workpack 内的紧密切片不重复创建 PRD 或 Issue。
- 研究阶段只产出学习记录、Gap、比较和候选，不创建实施 Workpack；候选被选中实施时使用新的正式阶段编号。
- 需求 Agent 只维护路线图候选、PRD、Issue 和需求状态；实现 Agent 只维护代码、测试与 Workpack evidence；Reviewer 默认只读。三种角色不得在同一轮交接中相互代替。
- 同一 worktree 同一时刻只允许一个写入者。存在未提交工件时，接手者必须使用原 worktree，并先核对 branch、base SHA、dirty-set、已完成切片和下一入口。
- 已进入实现且受历史链接或机器 allowlist 约束的旧文件名不在中途强行重命名；以 PRD frontmatter `phase`、Issue 标题和路线图阶段为准，阶段收口后再处理命名债务。

## 域结构（域 + 阶段两级）

| 域 | 文件夹 | 主题 |
|---|---|---|
| 会话工作台 | `session/` | 会话/消息/Run/SSE/Trace/调查发起 |
| 服务中心 | `service-center/` | 服务接入/连接状态/监控入口/服务上下文 |
| 服务监控 | `monitor/` | 快照/历史趋势/告警 |
| 模型设置 | `model/` | Provider/调用策略/API Key |
| 审批与受控动作 | `approval/` | 提案/人工审批/白名单执行/Verify |
| 知识库 | `knowledge/` | Markdown 检索/RAG/文档知识 |
| 审计/操作记录 | `audit/` | 跨服务跨会话的审计活动检索 |
| Agent 运行层 | `agent-runtime/` | Coordinator/领域 Agent/质量复核/结果汇总/安全 Trace |

## 当前进展

| 阶段 | 主题 | PRD | 状态 |
|---|---|---|---|
| P4.2 | 会话 DBAgent 工具接真实 PostgreSQL | `session/P4.2-db-agent-real.md` | 完成 |
| P4.3 | 会话服务上下文贯通与服务选择 | `session/P4.3-service-context.md` | 完成 |
| P4.3 | 模型设置页读取真实生效配置 | `model/P4.3-model-settings-real.md` | 完成 |
| P6 | 模型 Provider 与 API Key 管理 | `model/P6-model-provider-key-management.md` | 完成 |
| P4.4 | 服务中心多服务实例接入 | `service-center/P4.4-service-instances.md` | 完成 |
| P5 | 服务监控历史趋势与页面内告警 | `monitor/P5-monitor-trends.md` | 完成 |
| P6 | 服务主机指标监控 | `monitor/P6-host-metrics-monitoring.md` | 完成 |
| P5 | 受控动作闭环变真——联合索引重建 | `approval/P5-controlled-action-real.md` | 完成 |
| P6 | 知识库——目录内 Markdown 确定性检索 | `knowledge/P6-knowledge-retrieval.md` | 完成 |
| P6 | Redis 服务接入与只读监控 | `service-center/P6-redis-service-monitor.md` | 完成 |
| P6 | 跨服务联合调查——会话多服务 + 多 Run 聚合 | `session/P6-cross-service-investigation.md` | 完成 |
| P6 | 日志真实源接入 | `session/P6-log-source-real.md` | 完成 |
| P4 | 服务中心快照变真（已交付，非本目录 PRD） | — | 完成 |
| P7 | 文档知识库页面——知识目录浏览与确定性检索 | `knowledge/P7-knowledge-page.md` | 完成 |
| P7 | 数据库深度只读诊断——锁与连接池（慢查询深化第一切片） | `session/P7-db-lock-connection-diagnostics.md` | 完成 |
| P7 | 服务监控概览页——多服务监控聚合（导航"服务监控"落地） | `monitor/P7-monitoring-overview-page.md` | 完成 |
| P8 | 服务中心服务注册——动态接入、管理与连接测试 | `service-center/P8-service-registration.md` | 完成 |
| P8 | 会话工作台闭环——独立消息、取消 Run 与全局提案列表 | `session/P8-workbench-loop-closure.md` | 完成 |
| P8 | 会话工作台生命周期闭环——归档浏览与恢复 | `session/P8-session-lifecycle-management.md` | 完成 |
| P8 | 模型设置——运行时切换 mock / real 模式 | `model/P8-model-mode-switch.md` | 完成 |
| P8 | 审计操作记录——跨服务跨会话的活动检索 | `audit/P8-audit-activity-log.md` | 完成 |
| P8 | 模型可用列表探测——Provider 侧模型枚举 | `model/P8-model-list-enumeration.md` | 完成 |
| P8 | 会话管理——全局 Run 列表与会话搜索 | `session/P8-session-management.md` | 完成 |
| P8 | 调查重跑——重新生成并关联原 Run | `session/P8-rerun-investigation.md` | 完成 |
| P8 | 模型调用参数暴露——temperature 等运行参数的受控配置 | `model/P8-model-params-config.md` | 完成 |
| P8 | 用量与成本统计——token 计数与花费查询 | `model/P8-model-usage-stats.md` | 完成 |
| P8 | 消息编辑与删除——会话消息更正 | `session/P8-message-edit-delete.md` | 完成 |
| P8 | 会话导出——会话记录留存与分享 | `session/P8-session-export.md` | 完成 |
| P8 | 监控阈值与关注项配置——采样点异常判定规则可调 | `service-center/P8-monitor-threshold-config.md` | 完成 |
| P8 | 知识文档列表分页——目录浏览容量化 | `knowledge/P8-knowledge-document-pagination.md` | 完成 |
| P8 | 审计导出——审计活动留档与外部核验 | `audit/P8-audit-export.md` | 完成 |
| P8 | Agent 运行真实性与评测基线 | `agent-runtime/P8-agent-runtime-truthfulness-evaluation.md` | 完成 |
| 完善收口 | Judge Runtime 真实性与配置面收口 | `agent-runtime/judge-runtime-truthfulness.md` | 完成 |
| 完善收口 | 结构化诊断结果真实性——事实来源与安全呈现 | `session/structured-diagnosis-result-truthfulness.md` | 已完成，待提交 |
| P10 | Agent Harness 契约内核与回归基线 | `agent-runtime/P9-harness-contract-kernel.md` | 完成（PR #118） |
| P11 | Agent Harness 真实运行安全门 | `agent-runtime/P11-harness-real-runtime-safety-gate.md` | 完成（PR #123） |

## 执行 AI 如何使用
- 拿到 PRD 后：只实现「范围」内能力，逐条过「验收标准」，达到「完成定义」。
- 不改「不做什么」清单里的东西；边界外需求回 PRD，不擅自扩展。
- 实现方式自定，但必须满足 PRD 的非功能需求、安全边界与降级策略。

## 阶段总览（参考 `docs/路线图.md`）
- P0 清理 ✅ / P1 大脑上线 ✅ / P2 工具网关 ✅ / P3 前端重构 ✅ / P4 服务中心变真 ✅ / P4.2 会话 DBAgent 接真库 ✅ / P4.3 模型设置真实化 ✅ / P4.3 服务上下文贯通 ✅ / P4.4 多服务实例接入 ✅
- P5 受控动作闭环变真 → P6+ 更多服务/模型/知识库
