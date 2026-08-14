---
title: 调查重跑——重新生成并关联原 Run
status: 完成
domain: session
phase: P8
issue: 65
updated: 2026-08-14
---

# 调查重跑——重新生成并关联原 Run · PRD

## 背景

会话工作台是产品主入口（`docs/产品定义.md` §2.1），但调查答得不好时用户**只能重新打一遍问题**，且会新建一个与上次完全无关的 Run（`docs/接口清单.md` 第一大模块"缺少"表："重跑 / 重新生成：答得不好只能重新打一遍问题，且会新建一个 Run，前后两次无关联"）。

现状：`POST /sessions/{id}/runs` 用幂等键 + 请求指纹（`_query_fingerprint`）防重复提交（`backend/src/application/services.py`），但**没有"重跑"语义**——用户想重试同一问题，要么改点字面让它绕过指纹（产生无关联新 Run），要么等超时。两次调查之间的关联关系（哪次是重试、结果是否不同）完全丢失。

关联：`docs/接口清单.md`（第一大模块缺表）、`docs/prd/session/P8-workbench-loop-closure.md`（#54，已交付独立消息/取消 Run，明确排除重跑）、`docs/prd/session/P8-session-management.md`（#64，全局 Run 列表，重跑后的关联关系应在此可见）、`docs/产品定义.md` §2.1（会话主入口）。

## 目标

1. 用户能对已结束的 Run **一键重跑**，重新发起相同调查，无需重打问题。
2. 重跑产生的 Run 与**原 Run 显式关联**（来源关系可追溯），不是无关联的新 Run。
3. 会话/Trace/全局 Run 列表如实反映"这是对某次调查的重试"。

## 用户故事

作为用户，我发起慢查询调查，回答不理想，应能在结果页点"重新生成"让系统用同一问题重新调查一次——以便对比两次结论，而不是重新打一遍问题产生一个孤立的新 Run。

## 范围

### 做什么
- 重跑入口：已结束的 Run（`succeeded` / `failed` / `cancelled`）提供重跑；重跑复用原问题的 query 与 service 上下文。
- 关联关系：重跑产生的新 Run 记录 `parent_run_id`（或等价来源字段），指向原 Run；原 Run 标记"已被重跑"（可追溯）。
- 前端适配：Run 详情/结果页提供"重新生成"按钮；全局 Run 列表（#64 交付后）可展示重跑关联关系。
- 幂等：重跑与普通创建的幂等语义一致（重跑也是创建，带幂等键，防重复点击）。

### 不做什么（明确排除）
- 不做"编辑后重跑"（改了问题再跑——那是普通创建，不走重跑语义）。
- 不做并发重跑限制的额外策略（同一 Run 同时发起多次重跑 → 靠幂等键防重复，具体限制 Design 定）。
- 不做重跑历史的独立页面（关联关系在既有 Run 详情/列表表达，不新建页面）。
- 不改变既有 `POST /sessions/{id}/runs` 的创建行为（重跑是新增端点或复用创建 + 来源参数，Design 定）。
- 不暴露证据原文、工具输出、CoT/Prompt 或凭据。

## 功能需求

### 1. 重跑调查
- **输入**：用户对已结束 Run 发起重跑。
- **行为**：
  - 仅对 `succeeded` / `failed` / `cancelled` 状态的 Run 可用；`queued` / `running` 的 Run 重跑返回明确错误（或前端禁用）。
  - 重跑复用原 Run 的 query 与 service 上下文，发起新 Run；新 Run 记录来源（`parent_run_id` 指向原 Run）。
  - 重跑是创建操作，带幂等键，防重复点击（与既有创建一致）。
  - 原 Run 标记"已被重跑"（可追溯关联）。
- **输出**：新 Run 被受理（202），关联关系已记录；前端进入新 Run 的跟踪。

### 2. 关联关系可追溯
- **输入**：新 Run / 原 Run 详情，或全局 Run 列表。
- **行为**：新 Run 详情展示"重跑自 Run X"；原 Run 展示"已被重跑为 Run Y"；全局列表可展示来源关系。
- **输出**：可追溯的关联展示。

### 3. 前端重跑入口
- **输入**：Run 详情/结果页。
- **行为**：已结束 Run 提供"重新生成"按钮；点击发起重跑并进入新 Run；按钮 loading 态防重复点击。
- **输出**：重跑交互闭环。

## 非功能需求
- **可靠**：重跑幂等（重复点击不产生重复 Run）；单次重跑失败不影响原 Run 与关联。
- **诚实**：重跑是独立调查，其结果如实展示，不标注为"与上次相同"；来源关系如实。
- **性能**：重跑复用既有创建链路，性能与普通创建一致。
- **安全**：重跑不暴露证据原文/工具输出/CoT/Prompt/凭据。

## 数据与接口影响
- 数据：Run 记录新增来源字段（`parent_run_id` 或等价），涉及数据库迁移；既有 Run 数据兼容（历史 Run 无来源字段视为普通 Run）。
- 接口：新增重跑端点（`POST /runs/{id}/rerun` 或等价，Design 定）；Run 详情/列表响应扩展来源字段（兼容扩展）。

## 验收标准
- [ ] AC1: 当对 `succeeded` / `failed` / `cancelled` 的 Run 发起重跑时，应发起新 Run 并记录与原 Run 的关联。
- [ ] AC2: 当对 `queued` / `running` 的 Run 发起重跑时，应返回明确错误（或前端禁用）。
- [ ] AC3: 重跑复用原 Run 的 query 与 service 上下文。
- [ ] AC4: 重跑是幂等操作——重复点击同一重跑请求不产生重复 Run。
- [ ] AC5: 新 Run 详情应展示"重跑自原 Run"的关联；原 Run 应展示"已被重跑"。
- [ ] AC6: 全局 Run 列表（若已交付 #64）可展示重跑关联关系。
- [ ] AC7: 重跑响应与详情不得包含证据原文、工具输出、CoT/Prompt、凭据/DSN/`sk-`。
- [ ] AC8: 前端已结束 Run 提供"重新生成"按钮，点击进入新 Run，按钮 loading 防重复。
- [ ] AC9: 历史 Run（无来源字段）按普通 Run 处理，不受影响。
- [ ] AC10: 回归 —— 既有 `test_api.py` / `test_p2_application_services.py` / `test_p5_controlled_action.py` 相关全绿；前端 `typecheck`/`test`/`build` 通过。

## 边界与约束
- 安全边界：重跑复用既有创建链路；不暴露证据原文/凭据。
- 降级策略：重跑失败 → 返回明确错误，原 Run 与关联不受影响；原 Run 已归档/删除 → 明确错误。
- 兼容性：既有 `POST /sessions/{id}/runs` 创建行为不变；Run 详情/列表响应兼容扩展。

## 完成定义（DoD）
- [ ] 全部 AC（AC1–AC10）通过
- [ ] 相关回归测试全绿
- [ ] `git status` 只出现本 PRD 允许的文件
- [ ] 重跑来源字段迁移执行成功（若涉及）
- [ ] 重跑接口与页面均无未脱敏内容
- [ ] 前端 `typecheck` / `test` / `build` 通过

## 开放问题
1. **重跑端点形态**：`POST /runs/{id}/rerun`（明确语义）还是复用 `POST /sessions/{id}/runs` + 来源参数？→ 推荐前者（语义清晰），Design 定。
2. **来源字段命名**：`parent_run_id` 还是 `rerun_of_run_id`？→ Design 定。
3. **重跑是否带幂等键**：复用既有 Idempotency-Key 头，还是重跑端点内置幂等？→ 推荐复用既有机制，Design 定。

## GitHub Issue（已确认后回填）
- issue：#65（https://github.com/wzhwwwzzzhhh/oper-mind/issues/65）
- 状态同步：issue 状态与 PRD 状态一致（已确认=open，完成=closed）；中间过程留在 workpack。
