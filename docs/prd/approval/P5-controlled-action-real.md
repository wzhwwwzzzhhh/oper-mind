---
title: 受控动作闭环变真——联合索引重建
status: 草稿
domain: approval
phase: P5
updated: 2026-08-05
---

# 受控动作闭环变真——联合索引重建 · PRD

## 背景
审批与受控动作闭环骨架已完整：后端 `ActionProposalData`/`ActionApprovalData`/`ActionExecutionData`/
`ActionVerificationData` 状态机（pending_approval → approved → executing → verifying → verified，
含 rejected/expired/blocked/failed）、事件、幂等、脱敏（`_safe_action_event_data`）、
`ControlledActionExecutor` 端口都已就位；前端 `ActionProposalPanel` 审批面板完整
（批准/拒绝/二次确认执行/独立 Verify 展示/事件时间线）。

**但闭环没有真实动作模板**：`ActionApplicationService.maybe_create_proposal_in_transaction` 目前
始终返回 `None`（注释明确"当前尚无已注册的具体动作模板"）。结果是——诊断 Run 成功后**从不生成提案**，
`ActionProposalPanel` 永不出现，审批→执行→Verify 闭环从未在真实场景走通。骨架是"死"的。

**现状缺口（本 PRD 需一并打通）**：当前 `DiagnosisResultData` 的结构化字段保守留空
（`ConservativeResultAssembler`/`KernelReportResultAssembler` 均返回 `root_causes=[]`、`requires_approval=False`），
**尚无"缺索引/seq scan"的收敛信号可供提案触发**。本 PRD 范围包含：让诊断链路能产出收敛的"缺索引"信号
（复用 DBAgent 只读工具能力，脱敏、不伪造），使提案生成有真实、可验证的触发输入。

同时 P4.2 已交付 DBAgent 只读工具（`explain_sql`/`show_index`/`show_create_table` 接真 PostgreSQL），
诊断已能发现"缺索引 → seq scan"这类问题；但缺索引只是被报告，没有受控修复路径。
前端 Modal 文案甚至已写好占位："系统只会对受控靶场执行**代码内固定的联合索引重建**，并在之后独立 Verify"。

本 PRD 把这条"死"骨架接到第一个真实动作：**对慢查询缺失的索引生成"联合索引重建"提案**，
经人工审批 → 白名单执行 → 独立 Verify 全链路，且**只连受控靶场（演示库），不连生产**。

关联：`docs/路线图.md`（第四阶段"将确有价值的风险动作接入提案→人工审批→白名单执行→Verify"）、
`docs/P4.2DBAgent真库Design.md`（只读工具与只读引擎，本 PRD 前置）、
`docs/P4服务中心变真Design.md` 与 `docs/P4.4服务中心接入与凭据Design.md`（DSN 命名空间、只读边界）、
`docs/产品定义.md`（会话主入口、受控 Connector/Tool、高风险动作人工审批）、
`docs/开发规范.md`（高风险动作必须服务器提案、人工审批、严格白名单执行、独立 Verify；禁止自动批准、通用执行器）。

## 目标
1. 诊断 Run 成功后，在可触发条件下生成"联合索引重建"固定提案（不可编辑，内容由结构化结果收敛）。
2. 提案经 local_operator 人工审批 → 二次确认 → **白名单执行**（只连受控靶场）→ **独立 Verify** 全链路真实走通。
3. 闭环只作用于**受控靶场/演示库**（或 mock 模式），**绝不连生产**；能力边界如实声明。
4. mock 模式（S1–S4）行为完全不变，不产生提案、不执行。

## 用户故事
作为运维工程师，我在会话里对慢查询完成诊断，报告指出某表缺索引。
当存在明确的可修复信号时，系统生成一个"联合索引重建"提案，我在会话页看到该提案，
确认风险后批准、二次确认执行；系统对**受控靶场**执行代码内固定的建索引动作，随后独立 Verify 是否命中索引。
我能清楚看到这是只作用于演示靶场的受控动作，绝不会动生产。

## 范围

### 做什么
- 打通诊断侧"缺索引"收敛信号：诊断链路能产出脱敏、可验证的缺索引信号（复用 DBAgent 只读工具能力），
  作为提案生成的触发输入；无信号不制造。
- 实现**联合索引重建**动作模板：诊断结果出现"缺索引/seq scan"信号时，生成固定提案
  （action_id 固定、目标表/列由结构化结果收敛、不含 SQL 原文到 Trace/前端）。
- 实现**受控执行器**（`ControlledActionExecutor`）：执行前重查前置条件（表仍存在、索引仍缺失），
  对**受控靶场**执行白名单内固定建索引动作（如 `CREATE INDEX ... CONCURRENTLY` 或等价的受控版本），
  执行后独立 Verify（EXPLAIN 确认索引命中 / 索引已存在）。
- 打通 `maybe_create_proposal_in_transaction`：Run 成功后按可触发条件生成提案（mock 模式不触发）。
- 前端 `ActionProposalPanel` 在提案存在时正常展示与操作（已就绪，补测试即可）。
- 诚实边界：全程标注"受控靶场 target 模式"，不声称连生产。

### 不做什么（明确排除）
- **不连真实生产/预发布库执行任何变更**：执行器只对受控靶场（演示库）或 mock 模式生效；
  生产/预发布实例即使已注册，也绝不作为动作执行目标（能力边界硬约束）。
- 不做通用 SQL 执行器 / 任意语句执行：动作**代码内固定**，不接受任意 SQL 参数。
- 不做自动批准 / 自动执行：每一步都需 local_operator 明确人工操作。
- 不做执行回滚（Verify 失败不自动回滚，如实提示，见既有 `ActionVerificationFailedError` 语义）。
- 不做多用户身份/RBAC/多人审批（仍是 local_operator 单操作者）。
- 不做 MySQL / Redis 的受控动作（仅 PostgreSQL 联合索引重建）。
- 不做告警 / 通知推送（动作结果只在页面/事件展示）。
- 不改 mock 数据源（`data/mock_db.py`、`data/scenarios.py`）与 S1–S4 评测路径。

## 功能需求

### 1. 诊断侧"缺索引"收敛信号 + 联合索引重建提案生成
- **输入**：诊断 Run 成功后的结构化结果（`DiagnosisResultData`）与来源服务。
- **行为**：
  - 诊断链路产出收敛的"缺索引/seq scan"信号（脱敏：不含 SQL 原文/表名外泄，可验证，不伪造）；
    有信号才可能生成提案。
  - 仅当存在该信号时生成提案；无信号不生成，不制造假修复。
  - 提案内容**不可编辑**：action_id 固定、目标表/列/索引由结构化结果收敛、verification_plan 固定；
    不含 SQL 原文、对象名外泄风险按脱敏规则处理。
  - **mock 模式不触发**（S1–S4 行为完全不变）。
- **输出**：一条固定 `ActionProposalData`（status=pending_approval，绑定来源 Run），
  或确认无信号时生成 `None`。

### 2. 受控执行器（白名单 + 前置复核 + Verify）
- **输入**：已批准的固定提案。
- **行为**：
  - **前置条件重查**：执行前确认目标表仍存在、索引仍缺失；不满足则安全拦截（blocked），不发送任何变更。
  - **白名单执行**：只对**受控靶场（演示库）**执行代码内固定的建索引动作，不接受任意 SQL 参数。
  - **独立 Verify**：执行后只读验证（EXPLAIN 确认索引命中 / 索引已存在），通过 → verified，不通过 → failed（不自动回滚）。
  - 连接失败/超时/未配置 → 对应安全终态（blocked/failed），不把异常详情外泄。
- **输出**：`ActionExecutionAttempt` + `ActionVerificationOutcome`（脱敏摘要，无凭据/无原始 SQL）。

### 3. 执行器装配与安全边界
- **输入**：依赖注入装配执行器到 `ActionApplicationService`。
- **行为**：
  - 执行器按**静态服务注册表**解析"受控靶场"目标，只接受演示库目标；真实生产/预发布实例被拒绝。
  - 执行器内部不持有跨 Run 的引擎单例，每次现建短生命周期只读/受控连接。
  - mock 模式下执行器不存在或明确拒绝，不产生副作用。
- **输出**：装配完成，`maybe_create_proposal_in_transaction` 在有信号时生成提案。

### 4. 前端审批面板打通（验证为主）
- **输入**：会话页 Run 关联提案。
- **行为**：`ActionProposalPanel` 在提案存在时展示（批准/拒绝/二次确认执行/Verify/时间线），
  状态流转正确。
- **输出**：用户可完成 审批 → 执行 → 查看 Verify 全流程（只作用于受控靶场）。

## 非功能需求
- **安全**：动作代码内固定，无任意 SQL 输入；只连受控靶场，拒绝生产；前置条件重查；独立 Verify；
  凭据/DSN/SQL 原文不进日志/Trace/前端/事件。
- **可靠**：无信号不生成提案；前置不满足 → blocked；连接失败/超时 → 安全终态；不抛异常炸页面。
- **诚实**：全程标注"受控靶场 target 模式"；mock 模式不产生提案；不自动批准、不自动执行、不自动回滚。
- **性能**：执行与 Verify 限时（复用 P4 引擎 3s 超时模式），不阻塞诊断主链。

## 数据与接口影响
- 数据：复用既有 action_* 表结构（proposal/approval/execution/verification/event/idempotency），
  **不新增表**；若有字段需要（如提案需记录目标表/列）以既有 `target` dict 承载，不新增迁移。
- 接口：复用既有 `/api/v1/action-proposals/...` 接口（GET/detail/events/approval/executions），
  **不新增接口**；前端审批面板已就绪。

## 验收标准
- [ ] AC1: mock 模式下（S1–S4），诊断 Run 成功后不生成提案，`ActionProposalPanel` 不出现，行为与改动前一致。
- [ ] AC2: 当诊断链路产出"缺索引/seq scan"收敛信号（复用 DBAgent 只读工具能力，脱敏、可验证）时，
      Run 成功后生成一条 status=pending_approval 的固定提案，绑定来源 Run，内容不可编辑。
- [ ] AC3: 当诊断结果无缺索引信号时，不生成提案（返回无提案，非错误）；既有保守组装器
      （无信号时结构化字段留空）行为不变。
- [ ] AC4: 提案不含 SQL 原文、凭据、DSN、内部请求 ID；Trace 与前端只展示脱敏摘要。
- [ ] AC5: 批准提案后，执行器在**受控靶场**执行代码内固定的建索引动作；执行前重查前置条件，
      目标表/索引缺失确认后才执行。
- [ ] AC6: 前置条件不满足（如表已不存在/索引已存在）时，执行被安全拦截为 blocked，不发送任何变更，
      不把异常详情外泄。
- [ ] AC7: 执行完成后独立 Verify（EXPLAIN 确认索引命中 / 索引已存在）；通过 → verified，不通过 → failed（不自动回滚）。
- [ ] AC8: 执行器对**真实生产/预发布实例**（即使已注册）拒绝执行变更，只接受受控靶场目标。
- [ ] AC9: 连接失败/超时/未配置时，执行进入对应安全终态（blocked/failed），不抛异常炸页面，
      不暴露异常详情。
- [ ] AC10: 前端审批面板在提案存在时完成 审批 → 二次确认执行 → 查看 Verify 全流程，状态流转正确；
      全程标注"受控靶场 target 模式"。
- [ ] AC11: 回归 —— 后端相关测试（含 action 状态机、审批/执行/Verify、P4.2 只读工具）全绿；
      `GET /services/{id}` 等既有接口契约不变；mock 评测路径（S1–S4）不受影响。

## 边界与约束
- 安全边界：只连受控靶场，拒绝生产；动作代码内固定，无任意 SQL；人工审批 + 二次确认；
  独立 Verify；凭据/DSN/SQL 原文不进日志/Trace/前端/事件。
- 降级策略：无信号不生成提案；前置不满足 → blocked；连接失败/超时/未配置 → 安全终态；均不抛异常。
- 兼容性：mock 评测（S1–S4）行为不变；既有审批接口契约不变；执行器为新增能力，不影响既有只读诊断。
- 工程闸门：本 PRD 涉及**新增受控执行/变更能力（写操作）**，按开发规范必须先完成 Design → Review →
  **用户确认**后才能实施；本 PRD 是需求层，不替代 Design 文档。

## 完成定义（DoD）
- [ ] 全部 AC（AC1–AC11）通过
- [ ] 相关回归测试全绿
- [ ] `git status` 只出现本 PRD 允许的文件
- [ ] 未新增公开接口、未新增数据库迁移、未新增凭据
- [ ] 未打印/记录 DSN，未写 SQL 原文/凭据，未改 mock 数据源
- [ ] 执行器明确只能连受控靶场，生产/预发布实例被拒绝（有测试锁定）

## 已确认决策
1. 第一个真实受控动作：**联合索引重建**（对慢查询缺失的索引生成提案）。
2. 执行器连接范围：**只连受控靶场（演示库）**，不连真实生产/预发布库。

## 开放问题
- 联合索引的具体定义（列组合、索引名、是否 `CONCURRENTLY`）由实施 Design 定稿，需 Review 确认；
  PRD 层只要求"代码内固定、白名单、受控靶场、独立 Verify"。
