---
title: 结构化诊断结果真实性——事实来源与安全呈现
status: 已完成，待提交
domain: session
phase: 完善阶段收口
issue: 101
updated: 2026-08-27
---

# 结构化诊断结果真实性 · PRD

## 背景

多 Agent 内核已能产出 `DiagnosisResultData`（summary / severity / confidence / root_causes /
evidence / impact / recommendations / risks / requires_approval / agent_summary / report_markdown），
并通过公开契约投影到前端 `DiagnosisResultPanel`。但当前存在两处产品诚实性缺口：

1. **事实来源缺口（P0-2）**：`backend/src/infrastructure/diagnosis/result_assembler.py`
   的两个组装器（`ConservativeResultAssembler` 与 `KernelReportResultAssembler`）从不填充
   `recommendations`（`:69` 硬编码空列表）与 `impact`（`DiagnosisResultData.impact` 默认 `None`，
   两处组装器都不设置）。而 `root_causes` / `severity` / `confidence` / `evidence` 只来自
   确定性只读 `EvidenceInvestigationResult`。结果是：**“处置建议”与“影响面”永远为空**，
   与产品定义“查看回答、证据摘要、建议、审批状态”的能力承诺（`docs/产品定义.md` §2.1）脱节。
2. **前端呈现缺口（P1-3，含 P0-4 复核修正）**：`DiagnosisResultPanel.tsx` 现已渲染
   `impact`（影响面，行 222-227）与 `recommendations`（处置建议，行 229-243）板块——
   **`docs/完善清单.md` P0-4 原“三板块被丢弃”记录已过时**，需在交付时同步修正。
   真实仍缺的是：`report_markdown` 报告全文不渲染、回答气泡为纯文本
   （`diagnosis-result.test.tsx:29,75-90` **明确断言不渲染 Markdown，测试锁死**而非疏漏，属 P1-3）；
   以及结构化字段整体为空时逐字段“服务未返回…”四连排空态是噪音（P1-3）。

本 PRD 属于体验驱动完善阶段收口：**只为诊断结果建立“事实可追溯、空态诚实、呈现完整”的边界**，
不新增 Agent 能力、不改变多 Agent 编排语义。

## 目标

1. 让 `recommendations` 与 `impact` 拥有确定性的、可追溯的事实来源（从已确认的白名单动作模板
   与确定性只读事实派生），**绝不能**从报告正文（Markdown 散文）反推事实。
2. 结构化诊断结果在真实链路（含真实缺失索引场景）中有值，且值可追溯到只读证据或白名单动作模板。
3. 前端完整呈现诊断结果（报告全文安全呈现），空态改诚实折叠，回答支持安全 Markdown 渲染。
4. 公开投影继续满足脱敏、最小披露、无 CoT / 无 Prompt / 无原始工具输出 / 无原始 SQL / 无凭据。

## 用户故事

- 作为运维用户，我在会话里完成一次缺索引调查后，应看到“处置建议”列出可审批的固定修复动作及其
  来源（受控靶场白名单动作模板），而不是一个空面板或一句“服务未返回处置建议”。
- 作为运维用户，当一次只读调查确实没有安全事实可给建议时，我应看到诚实的“无建议/无证据”，
  面板整体折叠，而不是误导性的“服务未返回…”占位噪音。
- 作为评审用户，我应能从结构化结果追溯到每条根因/证据/建议的确切来源（确定性只读收集器
  或白名单动作模板），确认没有从报告散文反推的伪事实。

## 范围

### 做什么

- **建议与影响面的事实来源**：`recommendations` 从“已确认的白名单动作模板”派生——当且仅当
  结构化调查事实（如 `missing_index` 收敛信号）满足某动作模板的触发条件时，产出对应建议；
  无触发条件时留空，保持诚实。`impact` 同样只从确定性只读事实（或动作模板声明）派生，无事实则留空，
  不虚构影响范围。动作模板列表与触发规则由本 PRD 的配套 Design 定稿，
  只复用既有 `approval/P5-controlled-action-real.md` 已确认的受控靶场动作边界。
- **结构化字段可追溯**：为 `root_causes` / `evidence` / `recommendations` 增加/保持来源归属
  （如 evidence 的 `source_type` / `source_name`，建议的来源动作模板 id），
  公开投影仅暴露脱敏的、可理解的来源类别。
- **前端完整呈现**：`DiagnosisResultPanel` 安全呈现 `report_markdown`（报告全文）；
  `impact` / `recommendations` 板块保持已存在渲染；与既有 `ActionProposalPanel` 的关系保持清晰
  （建议 ≠ 提案，提案仍需人工审批，建议只是说明性条目）。
- **空态诚实化**：结构化字段整体为空时折叠为一句诚实文案（如“只读调查未产生可展示的结构化证据”），
  不再逐字段渲染“服务未返回…”的四连排空噪音；可保留摘要与报告正文。
- **安全 Markdown 渲染**：回答气泡与报告全文引入白名单化的轻量 Markdown 渲染
  （react-markdown 等，严格 sanitize，禁脚本/链接注入），替代纯文本直出；
  **同步更新 `diagnosis-result.test.tsx` 中“禁止渲染 Markdown”的既有断言**（P1-3 测试锁死需解除）。
- 交付时同步 `docs/完善清单.md` P0-2 / P0-4 / P1-3 与 `docs/跑通验证.md` C1/C5 状态与验证证据。

### 不做什么（明确排除）

- 不改变多 Agent 编排语义、路由策略或 Agent 顺序；不加 Knowledge Agent 进 chain。
- 不从报告正文 / Markdown 散文提炼或反推任何结构化字段（沿用保守留空的安全设计）。
- 不新增公开 API 字段契约；不改变既有 `DiagnosisResultData` / 资源的公开字段结构。
- 不新增数据库迁移、不新增 Connector / 服务类型 / 真实外部连接。
- 不扩大审批 / 执行能力边界；建议只作为说明性条目，不替代或自动触发提案。
- 不实现长期记忆、RAG、向量检索或 MCP。
- 不展示 CoT、系统 Prompt、工具实参、原始工具输出、原始异常、原始 SQL、DSN、API Key 或凭据。

## 功能需求

### 1. 建议（recommendations）与影响面（impact）的可追溯事实来源

- **输入**：一次结构化调查的确定性事实（`EvidenceInvestigationResult` 与收敛信号，如 `missing_index`），
  以及已确认的白名单动作模板字典。
- **行为**：
  - 当某白名单动作模板的触发条件被确定性事实满足时，从其模板派生一条脱敏 `recommendation`
    （含来源动作模板 id / 类别 / 摘要，不含 SQL 原文或对象名外泄）。
  - 当不存在满足条件的动作模板或事实不充分时，返回空列表（非错误），保持诚实。
  - `impact` 只从确定性只读事实（或动作模板声明的受影响范围）派生，无事实则留空，不虚构。
  - 每条建议可追溯到来源类别；绝不从报告正文推导。
- **输出**：与确定性事实一致的 `recommendations` 列表（可能为空）与 `impact`（可能为 null）。

### 2. 结构化字段来源可追溯

- **输入**：诊断结果的结构化字段。
- **行为**：根因 / 证据 / 建议的来源类别可被安全地读出并展示（脱敏），
  评审可按来源区分“确定性只读收集器”与“白名单动作模板”。
- **输出**：公开投影中的脱敏来源归属。

### 3. 前端完整呈现与空态诚实化

- **输入**：成功的诊断结果。
- **行为**：
  - 安全呈现 `report_markdown`（报告全文）；`impact` / `recommendations` 板块保持原有渲染。
  - 无值时诚实折叠，不逐字段刷“服务未返回…”。
  - 回答气泡 / 报告全文使用白名单 Markdown 安全渲染，并解除既有“不渲染 Markdown”测试断言。
- **输出**：完整、诚实、可读的诊断结果面板。

### 4. 安全 Markdown 渲染

- **输入**：回答正文与 `report_markdown`。
- **行为**：白名单化渲染（标题 / 段落 / 列表 / 代码块 / 表格 / 引用），
  禁用脚本、`on*`、`javascript:`、外部图片加载、任意 HTML 注入。
- **输出**：安全渲染后的富文本，不含可执行或外链风险。

### 5. 真实链路验证

- **输入**：真实受控靶场缺失索引场景 + 一次完整调查。
- **行为**：结构化字段（含建议与影响面，若有触发模板）有值且可追溯；真实链路闭环复核。
- **输出**：`docs/跑通验证.md` C1 / C5 与 `docs/完善清单.md` P0-2 / P0-4 / P1-3 状态更新。

## 非功能需求

- **诚实性**：无事实则无建议/影响面；空态用一句诚实文案；绝不从散文反推事实。
- **安全**：公开投影只含角色、阶段、状态、耗时、工具类别与脱敏证据摘要；无 CoT / 无原始 SQL / 无凭据。
- **可追溯**：每条结构化值可定位到来源类别（确定性只读事实或白名单动作模板）。
- **美观/可读**：空态收敛、Markdown 安全渲染，视觉与前文会话一致。

## 数据与接口影响

- 数据：无新增持久化，无数据库迁移；`recommendations` / `impact` 仍复用既有公开字段，
  仅改变其内容来源。
- 接口：无新增公开 API；既有 `DiagnosisResultData` / 资源 / 前端投影字段结构不变。

## 验收标准

- [x] AC1: 当某白名单动作模板的触发条件被确定性事实满足时，诊断结果 `recommendations` 非空，
      每条建议可追溯来源动作模板，且不含 SQL 原文 / 对象名外泄 / 凭据。
- [x] AC2: 当没有任何动作模板触发时，`recommendations` 返回空列表、`impact` 为 null（非错误），
      保持既有保守组装器行为。
- [x] AC3: 后端**不得引入**从 Markdown / 报告正文反推结构化字段的路径；评测用负向样例证明
      “报告正文与结构化字段不一致/反推”会被捕获并判失败。
- [x] AC4: 前端安全呈现 `report_markdown` 报告全文；`impact` / `recommendations` 板块渲染保持；
      测试 mock 非空值（含报告全文）可被渲染出，且既有“不渲染 Markdown”断言已按本 PRD 更新。
- [x] AC5: 结构化字段整体为空时，面板展示一句诚实空态并折叠，不再逐字段“服务未返回…”。
- [x] AC6: 回答与报告全文为白名单 Markdown 渲染；`<script>`、`on*`、`javascript:`、外链图片被禁用或脱敏。
- [x] AC7: 公开 Trace / 结果 / 日志不含 CoT、Prompt、工具实参、原始工具输出、原始异常、原始 SQL、路径或凭据。
- [x] AC8: 真实受控靶场缺失索引链路复核后，结构化字段（含建议与影响面，若有）有值且可追溯；
      `docs/完善清单.md` P0-2 / P0-4 / P1-3 与 `docs/跑通验证.md` C1/C5 按实测状态更新
      （不得仅因代码完成标 ✅；P0-4 过时记录一并修正）。
- [x] AC9: 未新增公开 API / 迁移 / Connector / 真实外部连接 / 高风险动作能力；既有接口契约不变。
- [x] AC10: 后端相关回归测试与前端 `typecheck` / `test` / `build` 全部通过。

## 边界与约束

- 安全边界：只读事实 + 白名单动作模板派生建议/影响面；绝不从散文反推；公开投影最小披露、无 CoT / 无凭据。
- 降级策略：无事实 → 无建议/影响面；整体空 → 诚实折叠空态；渲染异常 → 回退为脱敏纯文本，不暴露原始内容。
- 兼容性：公开字段契约不变；mock 场景行为（S1–S4）除建议/影响面事实来源外保持确定性；
  real 路由与编排顺序不变。
- 工程闸门：本 PRD 会改变 `recommendations` / `impact` 的事实来源
  （`docs/开发规范.md` §7.2“结构化结果的事实来源变更”），实施前须经 `arch-design`
  明确动作模板字典、触发规则与来源归属，再经 Review 与用户确认。

## 完成定义（DoD）

- [ ] 全部 AC（AC1–AC10）通过。
- [ ] `recommendations` / `impact` 事实来源为白名单动作模板与确定性只读事实，评测能捕获任何反推路径。
- [ ] 后端全量测试通过；前端 `typecheck` / `test` / `build` 通过。
- [ ] `git diff --check` 通过，改动范围只含本 PRD 及后续确认 Design / 工作包允许的文件。
- [ ] 未新增公开 API、迁移、Connector、真实外部连接、长期记忆或高风险动作。
- [ ] 公开 Trace、结果、日志、测试输出不含 CoT、Prompt、原始工具输出、原始异常、原始 SQL、路径或凭据。
- [ ] `docs/完善清单.md` 与 `docs/跑通验证.md` 已按真实验证结果同步，工作包证据可追溯到各 AC。

## 开放问题（待 Design 定稿后关闭）

- 白名单动作建议模板的“结构化字典”与触发规则（只覆盖联合索引重建，还是扩展）——由配套 Design 定稿，
  需 Review 确认，不改变本 PRD 的能力边界。
- `recommendations` / `impact` 条目与 `ActionProposalPanel` 提案的关系与展示边界
  （说明性建议 ≠ 可审批提案；影响面只来自确定性事实）。

## GitHub Issue（已确认后回填）

- issue：[#101](https://github.com/wzhwwwzzzhhh/oper-mind/issues/101)——结构化诊断结果真实性
  （指向体验驱动完善阶段 P0/P1 收口）。
- 状态同步：issue 状态与 PRD 状态一致（已确认=open，完成=closed）；中间过程留在 workpack。
