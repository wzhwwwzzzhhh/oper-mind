---
title: 消息编辑与删除——会话消息更正
status: 完成
domain: session
phase: P8
issue: 75
updated: 2026-08-15
---

# 消息编辑与删除——会话消息更正 · PRD

## 背景

会话工作台是产品主入口（`docs/产品定义.md` §2.1），用户在同一会话中持续追问。但**消息发出后无法更正**：用户问题打错了只能再发一条（污染上下文），发完的普通消息不能删（`docs/接口清单.md` 第一大模块"缺少"表："消息编辑 / 删除：发错了不能改。❌ 欠账（优先级低）"）。

现状：`GET /sessions/{id}/messages`（列表）+ `POST /sessions/{id}/messages`（普通消息轻量回复）已交付（P8 工作台闭环，issue #54）；消息模型 `MessageData`（`backend/src/domain/records.py`）含 `id / session_id / run_id / role（user/assistant/system）/ content / created_at`，持久化端口 `MessageRepository`（`backend/src/domain/repositories.py`）目前只有 `add` / `get_by_id` / `list_by_session`，**无更新、无删除**；API 层无 `PATCH/DELETE /sessions/{id}/messages/{message_id}` 路由。

关联：`docs/接口清单.md`（第一大模块缺表）、`docs/prd/session/P8-workbench-loop-closure.md`（#54，独立消息已交付）、`docs/产品定义.md` §2.1（会话主入口，消息可被安全关联和恢复）、`docs/开发规范.md` §2（会话消息必须可被安全地关联和恢复）。

## 目标

1. 用户能**编辑自己发出的普通消息**内容，更正打错的问题或补充信息。
2. 用户能**删除普通消息**（含对应回复的可见性处理），避免错发消息污染会话。
3. 更正行为**诚实留痕**：编辑后的消息如实标注"已编辑"；对调查上下文的影响如实处理，不伪造"重跑"或"原样"。

## 用户故事

作为用户，我在会话里把问题打错了，应能编辑这条消息更正内容，而不是再发一条（以免污染上下文）——以便会话记录与真实意图一致；发错且无价值的消息应能删除——以便会话干净可读。

## 范围

### 做什么
- 编辑普通消息：`PATCH /sessions/{id}/messages/{message_id}`，更新 user 消息内容。
- 删除普通消息：`DELETE /sessions/{id}/messages/{message_id}`，逻辑删除（历史不可丢）或物理删除（Design 定），会话内不再展示。
- 前端适配：会话消息操作（编辑 / 删除），编辑态替换原消息，删除后消息消失（含成对回复的可见性处理）。
- 已编辑标注：消息资源新增"已编辑"标记（如 `edited_at`），前端如实展示"（已编辑）"。

### 不做什么（明确排除）
- 不编辑 / 删除 **assistant（AI 回答）与 system 消息**：回答是调查产物，编辑会造成"用户改了 AI 结论"的误导；只允许编辑/删除 user 消息（Design 若需放宽须用户确认）。
- 不编辑 / 删除与 **Run 关联的输入消息**（`DiagnosisRunData.input_message_id` 指向的消息）的关联关系：删除消息不删除 Run、不删历史留痕（`docs/开发规范.md` §4：历史不可丢）；Run 详情仍可追溯。
- 不做"编辑后自动重跑"：编辑已产生 Run 的输入消息，不自动触发重新调查（那是 `POST /runs/{id}/rerun` 的语义，见 `P8-rerun-investigation.md`）。
- 不新增审批 / 权限模型（无登录体系，`docs/产品定义.md` §7 未决）。
- 不暴露证据原文、工具输出、CoT/Prompt 或凭据；编辑/删除接口不触碰 Run 结果与证据。

## 功能需求

### 1. 编辑消息（PATCH /sessions/{id}/messages/{message_id}）
- **输入**：会话 ID + 消息 ID + 新内容（非空、限长，与创建消息同约束）。
- **行为**：
  - 仅 `user` 角色消息可编辑；`assistant` / `system` 返回明确错误（如 422）。
  - 更新内容并记录 `edited_at`；会话消息列表按原时间线展示编辑后内容，标注"已编辑"。
  - 消息所属会话不存在 / 消息不存在 / 消息不属于该会话 → 404；空内容 / 超长 → 422。
- **输出**：更新后的消息资源（含 `edited_at`），时间线位置不变。

### 2. 删除消息（DELETE /sessions/{id}/messages/{message_id}）
- **输入**：会话 ID + 消息 ID。
- **行为**：
  - 仅 `user` 角色消息可删除；`assistant` / `system` 返回明确错误。
  - 删除后该消息不再出现在 `GET /sessions/{id}/messages` 列表；关联的 Run（若有）与历史留痕不删除（Run 详情仍可追溯）。
  - 重复删除 / 已删除消息 → 幂等成功（204）或明确 404（Design 定，与既有 `DELETE /sessions/{id}` 幂等语义对齐）。
- **输出**：204；会话消息列表不再出现该消息。

### 3. 已编辑标注与前端适配
- **输入**：会话消息列表 / 消息操作入口。
- **行为**：编辑后的消息展示"已编辑"标记；前端提供编辑（进入编辑态 → 保存 → 替换展示）与删除（确认 → 移除）操作；删除带回复的消息时如实提示影响（如"该问题已有调查回答，删除问题不删除回答记录"）。
- **输出**：会话内消息可编辑/删除的交互闭环，空态/失败态诚实展示。

## 非功能需求
- **诚实**：编辑消息标注"已编辑"；删除消息不影响 Run 历史；不伪造时间线顺序或重跑关系。
- **安全**：只读默认；编辑/删除不改变 Run、结果、证据、审批与留痕；不暴露凭据/证据原文/工具输出。
- **一致性**：编辑后内容在会话列表、消息详情（若存在）处处一致；删除后列表不再出现。
- **性能**：单消息编辑/删除为点操作，不引入额外查询放大。

## 数据与接口影响
- 数据：消息表新增可空 `edited_at` 字段（涉及数据库迁移，Design 定列名与 nullable）；删除采用软删除（`archived_at`，复用 `TimestampedRecord`）或物理删除（Design 定），历史留痕不丢。
- 接口：新增 `PATCH /sessions/{id}/messages/{message_id}`、`DELETE /sessions/{id}/messages/{message_id}`；`MessageResource` 增加 `edited_at`（可空）；既有 `GET/POST` 消息契约不变（列表返回 `edited_at`）。

## 验收标准
- [ ] AC1: 当 PATCH 编辑一条 user 消息时，应更新内容并返回含 `edited_at` 的消息资源，时间线位置不变。
- [ ] AC2: 当 PATCH 编辑 assistant/system 消息时，应返回明确错误（422），消息不变。
- [ ] AC3: 当 PATCH 编辑不存在的消息、或消息不属于该会话时，应返回 404。
- [ ] AC4: 当 PATCH 提交空内容或超长内容时，应返回 422。
- [ ] AC5: 当 DELETE 删除一条 user 消息时，应返回 204，且该消息不再出现在会话消息列表。
- [ ] AC6: 当 DELETE 删除 assistant/system 消息时，应返回明确错误（422），消息保留。
- [ ] AC7: 当删除与 Run 关联的消息时，应不影响该 Run 的详情与历史留痕（Run 仍可追溯）。
- [ ] AC8: 当重复删除同一消息时，应按幂等语义返回（204 或明确 404），不产生错误副作用。
- [ ] AC9: 当前端编辑消息后，应展示"已编辑"标注；删除后消息消失，空态/失败态诚实展示。
- [ ] AC10: 回归 —— 既有 `test_api.py` / 会话消息相关测试全绿；前端 `typecheck`/`test`/`build` 通过。

## 边界与约束
- 安全边界：只读默认；编辑/删除不触碰 Run、结果、证据、审批与凭据；不暴露证据原文/工具输出/CoT。
- 降级策略：消息不存在 / 无权限（无身份模型下为资源归属校验）→ 明确错误；删除关联消息 → Run 历史不受影响。
- 兼容性：既有 `GET/POST` 消息契约不变；无 `edited_at` 的历史消息正常返回（字段可空）。

## 完成定义（DoD）
- [ ] 全部 AC（AC1–AC10）通过
- [ ] 相关回归测试全绿
- [ ] `git status` 只出现本 PRD 允许的文件
- [ ] 迁移执行成功（若新增 `edited_at`/软删除列）
- [ ] 前端 `typecheck` / `test` / `build` 通过
- [ ] 编辑/删除接口与页面均不含证据原文/工具输出/凭据

## 开放问题
1. **删除范围**：是否允许删除"已有 Run 关联的 user 消息"？推荐允许（仅从消息列表移除，Run 留痕保留），Design 确认。
2. **删除实现**：软删除（`archived_at`）还是物理删除？推荐软删除（历史可审计），Design 定。
3. **assistant 消息**：是否允许删除成对的 assistant 回复（跟随 user 消息一起删）？推荐仅 user 消息可删，assistant 回复随其输入 user 消息删除而不再展示（不物理删 Run 记录），Design 确认。
4. **编辑对调查上下文的影响**：编辑已产生 Run 的输入消息是否影响后续追问的上下文？推荐"编辑仅改展示，不重放上下文"，Design 定。

## GitHub Issue（已确认后回填）
- issue：（待用户确认后建）
- 状态同步：issue 状态与 PRD 状态一致（已确认=open，完成=closed）；中间过程留在 workpack。
