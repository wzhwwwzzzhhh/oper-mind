---
title: 审计操作记录——跨服务跨会话的活动检索
status: 完成
domain: audit
phase: P8
issue: 62
updated: 2026-08-12
---

# 审计操作记录——跨服务跨会话的活动检索 · PRD

## 背景

`docs/产品定义.md` §4 把「审计」写进**安全治理层**责任（"凭据、权限、允许资源、只读边界、审批、白名单执行、验证和审计"），但当前系统没有任何地方能回答"系统这周对我的服务做了什么、谁批的"——只有 `GET /services/{id}/activities` 能按单个服务看绑定会话的 Run 与修复闭环，跨服务跨会话的全局活动视图不存在。

`docs/接口清单.md` 第五部分把审计列为**建议且风险最低**的管理："数据（runs + action events）已在库里，主要是加一层跨服务跨会话的列表与过滤接口。"该部分还记录用户 2026-08-09 确认"先把四个模块做完，暂不铺第五个模块"——四个模块（会话/服务中心/知识库/模型）的 PRD 已齐（P8 #53/#54/#55 已确认），审计作为第五个跨模块管理能力现在排上。

现有数据事实（`backend/src/infrastructure/persistence/models.py`）：`DiagnosisRunRecord`（调查 Run）、`ActionProposalRecord`（提案）、`ActionEventRecord`（动作事件，含 proposal_created / approval_recorded / execution_* / verification_* 等）均已在库；`service_center.py` 的 `list_activities` 已有按服务聚合的安全摘要先例（`GET /services/{id}/activities`）。审计只需在其基础上加跨服务跨会话的全局检索。

已知边界：`POST /approval` 无审批人身份（`docs/产品定义.md` §7 未决，身份模型是前置），因此审计记录中的"审批人"字段当前无法可靠填值——本 PRD 如实标注，不伪造审批人。

关联：`docs/产品定义.md` §4（安全治理层含审计）、`docs/接口清单.md` 第五部分（审计建议）、`docs/prd/service-center/P8-service-registration.md`（同批 P8，审计覆盖其注册/移除/测试连接动作）、`docs/完善清单.md` P1-11（提案审批 UI 体验）、`docs/prd/approval/P5-controlled-action-real.md`（受控动作闭环）。

## 目标

1. 运维能按时间窗、服务、动作类型、结果检索跨会话跨服务的审计活动记录。
2. 审计记录覆盖调查 Run 与受控动作（提案/审批/执行/验证）的安全摘要，不含原始证据、工具输出或凭据。
3. 与既有 `GET /services/{id}/activities` 的脱敏纪律一致，诚实降级。

## 用户故事

作为运维工程师，我想知道"这周系统对我的生产库做了什么、哪些提案被批准了"，应有一个跨服务跨会话的审计列表，按服务/时间/类型过滤——以便满足合规审查与安全留痕。

## 范围

### 做什么
- 新增审计检索接口（跨服务跨会话）：
  - 活动列表：`GET /audit/activities`，支持时间窗（from/to）、服务 ID、动作类型、结果过滤，cursor 分页。
  - 覆盖两类活动：调查 Run（跨服务跨会话的安全摘要）与受控动作事件（提案/审批/执行/验证）。
- 复用 `service_center.list_activities` 的安全摘要收敛逻辑（脱敏、限长、不含原始证据）。
- 前端新增审计/操作记录入口页（列表 + 过滤），或并入既有服务中心/会话页（Design 定）。

### 不做什么（明确排除）
- 不做身份/审批人模型（`docs/产品定义.md` §7 未决，前置；审批人字段当前诚实标注为不可可靠填值）。
- 不做日志/Trace 原始事件检索（Trace 只是 Run 事件安全投影，审计检索同样不暴露 CoT/Prompt/原始 SQL）。
- 不做告警通知 / 导出 / 报表（另行排期）。
- 不暴露凭据、完整 DSN、`sk-` 内容、原始工具输出或异常详情。
- 不改变既有 `GET /services/{id}/activities` 行为与契约。

## 功能需求

### 1. 审计活动列表（GET /audit/activities）
- **输入**：可选过滤（from/to 时间窗、service_id、动作类型、结果状态），cursor 分页。
- **行为**：
  - 跨会话跨服务返回审计活动安全摘要（活动 id/类型/时间/关联服务/会话/结果/脱敏摘要）。
  - 动作类型过滤覆盖调查 Run（run_created / run_completed / run_failed 等）与受控动作（proposal_created / approval_recorded / execution_completed / verification_completed 等）。
  - 结果过滤（succeeded / failed / pending_approval / approved 等）。
  - 未匹配到服务 ID 时返回空列表，不抛错。
- **输出**：审计活动分页列表；无记录时诚实空态。

### 2. 前端审计入口
- **输入**：全局导航或服务中心子导航的"审计/操作记录"入口。
- **行为**：列表页展示审计活动，支持过滤；点击某项可进入对应 Run/提案详情（若可定位）。
- **输出**：审计页面；空态/失败态诚实展示。

## 非功能需求
- **安全**：审计检索与既有 `activities` 同脱敏纪律——不含证据原文、原始工具输出、原始 SQL、异常详情、凭据/DSN/`sk-`。
- **诚实**：审批人字段当前无可靠身份来源，如实标注为"未记录"而非伪造；空结果诚实空态。
- **性能**：列表为库内查询 + 脱敏收敛，分页限长（对齐既有 `activities`）。
- **可靠**：过滤参数非法时返回明确错误；单服务无记录不影响整体。

## 数据与接口影响
- 数据：无新增持久化、无迁移（复用 runs / action proposals / action events 三张既有表）。
- 接口：新增 `GET /audit/activities`；既有 `GET /services/{id}/activities` 契约不变。

## 验收标准
- [ ] AC1: 当请求 `GET /audit/activities` 时，应返回跨会话跨服务的审计活动安全摘要分页列表。
- [ ] AC2: 当用时间窗（from/to）过滤时，应只返回窗口内的活动。
- [ ] AC3: 当用 service_id 过滤时，应只返回该服务的活动；不存在的 service_id 返回空列表不抛错。
- [ ] AC4: 当用动作类型过滤时，应只返回匹配类型的活动（覆盖调查 Run 与受控动作两类）。
- [ ] AC5: 当用结果状态过滤时，应只返回匹配结果的活动。
- [ ] AC6: 审计活动摘要不得包含证据原文、原始工具输出、原始 SQL、异常详情、凭据/DSN/`sk-`。
- [ ] AC7: 审批人字段无可靠身份来源时，应如实标注为"未记录"，不伪造审批人。
- [ ] AC8: 无匹配记录时返回空列表（诚实空态），不抛错。
- [ ] AC9: 既有 `GET /services/{id}/activities` 行为与契约不变。
- [ ] AC10: 前端审计入口可访问，支持过滤，空态/失败态诚实展示；`typecheck`/`test`/`build` 通过。
- [ ] AC11: 回归 —— 既有 `test_service_center` / `test_p2_application_services` / `test_p5_controlled_action` 相关全绿。

## 边界与约束
- 安全边界：审计检索只读；脱敏纪律与既有 `activities` 一致；不暴露凭据/原始数据。
- 降级策略：无匹配 → 空态；过滤非法 → 明确错误；审批人无来源 → 如实标注。
- 兼容性：既有接口契约不变；mock 模式行为一致；不新增凭据/迁移。

## 完成定义（DoD）
- [ ] 全部 AC（AC1–AC11）通过
- [ ] 相关回归测试全绿
- [ ] `git status` 只出现本 PRD 允许的文件
- [ ] 未新增持久化/迁移/凭据
- [ ] 审计接口与页面均无未脱敏内容
- [ ] 前端 `typecheck` / `test` / `build` 通过

## 开放问题
1. **审计入口放哪**：全局导航（与服务中心并列）还是服务中心子导航？→ Design 定。
2. **动作类型枚举**：覆盖哪些类型（run + action 事件的全集还是收敛子集）？→ Design 定，默认收敛为安全摘要可表达的有限枚举。
3. **审批人字段处理**：无身份模型时，是显示"未记录"还是完全隐藏该列？→ 推荐前者（诚实标注）。

## GitHub Issue（已确认后回填）
- issue：#62（https://github.com/wzhwwwzzzhhh/oper-mind/issues/62）
- 状态同步：issue 状态与 PRD 状态一致（已确认=open，完成=closed）；中间过程留在 workpack。
