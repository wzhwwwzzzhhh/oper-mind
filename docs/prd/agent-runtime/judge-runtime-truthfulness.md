---
title: Judge Runtime 真实性与配置面收口
status: 完成
domain: agent-runtime
phase: 完善阶段收口
issue: 104
updated: 2026-08-27
---

# Judge Runtime 真实性与配置面收口 · PRD

## 背景

P0-6 记录了"配置面与行为面脱节"：`judge_llm` 配置、接口与前端展示齐全，
但**全系统无任何执行节点使用**——Debate / Reflection 实际用主 `llm`
（`backend/src/core/debate.py:74`、`backend/src/core/reflection.py:88,111`，注释仍写"简化实现"）。

在 P8 模型域交付后，现状进一步明确：

- 后端仍提供 env 配置段 `judge_llm`（`config.py:18-20` `OPERMIND_JUDGE_*`），并在
  `GET /model/config` 的 `judge_model` 与前端"裁判模型"卡片中展示（`routes.py:393`、`model_providers.py:345`）。
- 同时，P6/P8 已落地 DB 激活的模型 Provider 通路，`active_endpoint` 已支持 `judge`（"裁判生效"），
  前端模型设置页有"设为裁判"按钮（`ModelSettingsPage.tsx:444`）。
- 但 **Debate / Reflection 质量节点仍然使用主诊断 `llm`，从不消费 `judge_llm` 配置或 `judge` 端点的 Provider**。

结果是产品诚实性缺口：**用户能在配置/页面看到"裁判模型 / 裁判生效"，但质量复核节点从不使用它**——
这会让用户误以为已有独立的裁判模型在运行，而实际上质量节点仍是主模型的简化实现。

同时 `P0-6` 还记录了若干无引用死代码：`backend/src/core/fallback.py`（`RuleEngine`，全项目无引用，
经核对仅 `fallback.py` 自身使用）、`backend/src/core/llm.py:_mock_response`（全项目无引用）等。

**本 PRD 已确认采用路径 B（轻量收回）**：这是产品级拍板（2026-08-27 用户确认）。
接线独立 Judge（路径 A）不改变本 PRD 结论，但保留为后续独立能力的方向说明，不在此实现。

## 目标

1. 消除"裁判模型"配置面 / 页面展示与执行行为脱节的诚实性缺口：**如实收回**"裁判模型 / 裁判生效"
   的未启用承诺，使配置面与执行行为一致。
2. 清理无引用死代码（`core/fallback.py`、`llm.py:_mock_response` 等）。
3. 质量节点现状不变（仍由主诊断模型承担），不改变多 Agent 编排语义。

## 用户故事

- 作为运维用户，我在模型设置页看到"裁判模型"，应能明确知道它**未启用**，或页面完全不再展示
  误导性的"裁判生效"，而不是配置了却从不生效。
- 作为研发评审，我希望知道当前质量节点的真实驱动来源，以及哪些配置 / 代码是死代码，
  避免维护员在无效配置上浪费时间。

## 范围

### 做什么（路径 B——如实收回，轻量）

- **收回误导配置面**：模型设置页与 `/model/config` 不再误导性展示"裁判生效"，
  或明确标注"未启用"；页面如实说明质量节点（Debate / Reflection）由主诊断模型承担，
  不提供看似存在的独立裁判能力。
- **env 配置段收敛**：`judge_llm` env 段（`OPERMIND_JUDGE_*`）与 DB `judge` endpoint 的
  收口范围由配套 Design 定稿（仅收展示层，或连 env/Endpoint 一并下线），不留下"配置了却从未生效"
  的死配置；公开 `GET /model/config` 契约结构不删字段，只收口内部值 / 文案为"未启用"或等价语义。
- **死代码清理**：删除或显式标注全项目无引用的 `core/fallback.py`（`RuleEngine`）与
  `llm.py:_mock_response`，并更新过时注释（如 `dependencies.py:97-98`"审批执行器仍为空骨架"）。
- 交付时同步 `docs/完善清单.md` P0-6、`docs/跑通验证.md` C3 与相应设计文档状态。

### 不做什么（明确排除）

- **不接线独立 Judge**（路径 A 不再本 PRD 实现）；不改变质量节点编排语义，质量节点仍由主模型承担。
- 不新增公开 API 字段、不改既定 `GET /model/config` 契约结构（收口只动内部接线/文案，不删字段）。
- 不新增数据库迁移、不新增 Connector / 服务类型 / 真实外部数据源。
- 不实现长期记忆、RAG、向量检索或 MCP。
- 不改变 DB / Server / Log / Knowledge Agent 的工具边界或路由策略
  （保留 P8 #98/#99 已确定的互斥角色白名单，不把 Knowledge Agent 加入 chain）。
- 不新增任意 SQL、Shell、DDL、DML、网络访问或高风险动作能力。
- 不把"独立裁判"做成对每个 Run 都强制的第二个模型调用（成本/延迟问题在本 PRD 不引入）。

## 功能需求

### 1. 收回误导承诺（路径 B）

- **输入**：当前模型设置页"裁判模型 / 设为裁判"展示与 `/model/config` 的 `judge_model` 段。
- **行为**：隐藏或标注"未启用"的 judge 展示；页面如实说明质量节点由主诊断模型承担；
  不提供看似存在的独立裁判操作路径。
- **输出**：不再误导用户的模型设置页与配置契约说明。

### 2. 质量节点如实标注

- **输入**：一次多 Agent 调查的质量节点（Debate / Reflection）状态。
- **行为**：质量节点继续由主诊断模型承担；系统如实标注驱动来源（主模型），
  不展示任何"已由独立裁判复核"的虚假语义。
- **输出**：与驱动来源一致的质量节点状态与安全 Trace。

### 3. 死代码与过时注释清理

- **输入**：`core/fallback.py`、`llm.py:_mock_response`、`dependencies.py:97-98` 过时注释等。
- **行为**：删除无引用死代码或显式标注用途；更新过时注释。
- **输出**：无无效引用、文档与现实一致。

### 4. 公开投影安全

- **输入**：质量节点运行产生的状态。
- **行为**：Trace 只展示角色、阶段、状态、耗时、工具类别与脱敏摘要；不暴露 CoT / Prompt / 原始工具输出。

## 非功能需求

- **诚实**：不再展示"裁判模型"却从不生效；质量节点驱动来源如实标注（主模型）。
- **安全**：公开投影无 CoT / 无凭据。
- **确定性**：mock 模式质量节点保持可复现，不受本次收口影响。
- **可维护**：死代码清理，减少无效维护面；恢复"配置=行为"的一致性。

## 数据与接口影响

- 数据：无新增持久化，无数据库迁移。
- 接口：无新增公开 API；`GET /model/config` 契约结构不变（只收口内部值/文案，不删字段）。

## 验收标准

- [ ] AC1(路径B): 模型设置页 / `/model/config` 不再展示"裁判生效"，或明确标注"未启用"；
      页面如实说明质量节点由主诊断模型承担。
- [ ] AC2(共同): `GET /model/config` 契约字段结构不变；`judge_model` 展示（若保留）只表达
      "未启用"或等价语义，不含任何已生效的误导承诺。
- [ ] AC3(共同): `core/fallback.py` 与 `llm.py:_mock_response` 无引用死代码已清理或显式标注用途。
- [ ] AC4(共同): 过时注释（如 `dependencies.py`"审批执行器仍为空骨架"）已更新为现实。
- [ ] AC5(共同): 质量节点由主诊断模型承担的驱动来源在 Trace/页面如实标注，
      不出现"已由独立裁判复核"的虚假语义。
- [ ] AC6(共同): 公开 Trace / 结果 / 日志不含 CoT、Prompt、原始工具输出、原始 SQL、路径或凭据。
- [ ] AC7(共同): DB / Server / Log / Knowledge Agent 工具边界与路由策略不变；
      P8 #98/#99 既有角色白名单与质量节点行为回归通过（mock 决定性、未执行状态如实）。
- [ ] AC8(共同): 未新增公开 API / 迁移 / Connector / 真实外部访问 / 高风险动作能力。
- [ ] AC9(共同): 后端相关回归测试与前端 `typecheck` / `test` / `build` 通过；
      `docs/完善清单.md` P0-6、`docs/跑通验证.md` C3 按实测状态更新。
- [ ] AC10(共同): 所选路径（B）经 Design → Review → 用户确认后实施，未擅自扩大能力边界。

## 边界与约束

- 安全边界：质量节点不与独立裁判接线，不外泄原始响应；公开投影无 CoT / 无凭据。
- 降级策略：质量节点由主模型承担；未配置/失败 → 如实标"未启用/失败"，不伪装"已复核"，
  不阻塞诊断主链的受控降级。
- 兼容性：既有公开 API 契约不变；mock 场景确定性保持；DB / Server / Log / Knowledge 工具边界不变。
- 工程闸门：本 PRD 会改变 `judge_llm` / judge endpoint 的配置面表达（收口），
  且清理无引用死代码，按 `docs/开发规范.md` §7.2 属"是否接线或收回配置面"的决策，
  须 Design → Review → 用户确认后再实施；同时同步更新 `docs/产品定义.md` §7 未决事项
  （"高危 SQL 审批是否重新设计"之外的未启用能力如实标注）。

## 完成定义（DoD）

- [ ] 全部 AC（AC1–AC10，按所选路径 B）通过。
- [ ] 所选路径（B）经 Design → Review → 用户确认后实施。
- [ ] 后端全量测试通过；前端 `typecheck` / `test` / `build` 通过。
- [ ] `git diff --check` 通过，改动范围只含本 PRD 及后续确认 Design / 工作包允许的文件。
- [ ] 未新增公开 API、迁移、Connector、真实外部连接、长期记忆或高风险动作。
- [ ] 公开 Trace、结果、日志、测试输出不含 CoT、Prompt、原始工具输出、原始异常、原始 SQL、路径或凭据。
- [ ] `docs/完善清单.md`、`docs/跑通验证.md`、`docs/产品定义.md`（如需）按最终决策同步。

## 开放问题（待用户确认/Design 定稿后关闭）

- **收口范围**：路径 B 是"仅收展示层（UI + 文案）"，还是"连 `OPERMIND_JUDGE_*` env 配置与
  DB `judge` endpoint 一并下线"？由配套 Design 定稿，需 Review 确认；两者都不删
  `GET /model/config` 公开字段结构。
- **后续方向**：若未来确需独立裁判（路径 A：让 Debate / Reflection 用独立 Judge 来源），
  应作为新的独立 PRD 走完整 Design → Review → 用户确认，不在本 PRD 实现。

## GitHub Issue（已确认后回填）

- issue：[#104](https://github.com/wzhwwwzzzhhh/oper-mind/issues/104)——Judge Runtime 真实性与配置面收口
  （指向体验驱动完善阶段 P0/P1 收口）。
- 状态同步：issue 状态与 PRD 状态一致（已确认=open，完成=closed）；中间过程留在 workpack。
