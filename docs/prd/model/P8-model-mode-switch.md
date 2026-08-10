---
title: 模型设置——运行时切换 mock / real 模式
status: 已确认
domain: model
phase: P8
issue: 55
updated: 2026-08-10
---

# 模型设置——运行时切换 mock / real 模式 · PRD

## 背景

模型设置页当前**只能读模式不能切**（`docs/接口清单.md` 第四大模块：`GET /model/config` 的 `mode` 字段只读）。`mode`（mock / real）完全由环境变量与 YAML 决定：`OPERMIND_API_KEY` 为 `mock` 即 mock 模式，否则 real。界面只能看到当前模式，切换要改配置重启。

P4.3 模型设置页真实化（`docs/prd/model/P4.3-model-settings-real.md`）已明确排除"切换 mode（mock↔real）"并注明须另行 PRD；P6 模型 Provider 管理（`docs/prd/model/P6-model-provider-key-management.md`）已落地 DB 激活 Provider 优先、env/YAML 兜底的生效配置机制。本 PRD 是这两个的后继：把模式从"环境决定"变为"运行时用户可切"，且与既有生效配置机制一致地诚实标注。

现状缺口：开发/演示时想临时切 real 模式验证真实模型，或想回到 mock 避免消耗，都要改环境变量重启后端——产品主入口（会话）的模型模式是产品体验的一部分，运行时切换是明确需求。

关联：`docs/接口清单.md`（第四大模块缺表）、`docs/prd/model/P4.3-model-settings-real.md`（只读展示已交付，明确 mode 不可切）、`docs/prd/model/P6-model-provider-key-management.md`（DB 激活 Provider 优先、加密 Key 已落地）、`docs/开发规范.md`（配置优先级：环境变量覆盖 YAML；`OPERMIND_API_KEY` 为 env 注入）。

## 目标

1. 运维能在模型设置页**运行时切换 mock ↔ real**，无需改配置或重启。
2. 切换后的模式**即时生效**于会话链路与 `GET /model/config`，与 DB 激活 Provider 的既有机制一致。
3. 模式状态**诚实持久化**（非前端 localStorage 假状态），重启后保持。

## 用户故事

作为运维工程师，我在开发环境验证真实模型调用时，应在模型设置页一键从 mock 切到 real，保存后会话链路立刻用真实模型——而不是改环境变量重启后端。

## 范围

### 做什么
- 运行时模式开关：前端模型设置页新增 mock / real 切换，保存到后端持久化。
- 生效机制：模式选择覆盖 env/YAML 决定（与 DB 激活 Provider 优先同理，模式是运行时配置）；`GET /model/config` 返回切换后的模式。
- 会话链路：会话/调查使用当前生效模式；切到 real 但无可用 Provider/API Key 时如实降级标注。
- 诚实标注：切换操作的前后端状态一致；real 模式但连接不可用时如实提示，不假装已切换成功。

### 不做什么（明确排除）
- 不做 Provider 下可用模型列表自动发现（接口清单欠账，另行排期）。
- 不做模型参数（temperature / max_tokens）暴露（接口清单欠账，需先定范围）。
- 不做用量/成本统计（接口清单欠账，另行排期）。
- 不做多模型路由策略（按 Agent 角色分配，`docs/产品定义.md` §7 未决）。
- 不改变 `OPERMIND_API_KEY` 等 env 的配置读取机制本身（模式是运行时覆盖层，env 仍是兜底事实）。
- 不把模式状态放前端 localStorage（`完善清单.md` P1-7 已删假开关，不复活本地假状态）。

## 功能需求

### 1. 运行时模式切换
- **输入**：模型设置页的 mock / real 切换操作。
- **行为**：
  - 切换值写入后端持久化（应用库，简单键值或复用既有配置表）。
  - 切换后 `GET /model/config` 返回新模式；会话链路按新模式运行。
  - real 模式但未配置可用 Provider/API Key 时，保存仍成功但页面如实提示"当前无可用 Provider，real 模式将不可用"。
- **输出**：模式已切换；`mode` 字段与页面状态一致。

### 2. 生效与兜底
- **输入**：会话/调查发起。
- **行为**：按持久化的模式解析生效配置；模式为 real 时走 DB 激活 Provider（未激活则 env/YAML 兜底）；无可用 Key 时诚实降级为 mock 或标注不可用，不伪造真实连接。
- **输出**：会话链路按生效模式运行；`GET /model/config` 与页面展示一致。

### 3. 诚实标注与一致性
- **输入**：任意读取 `GET /model/config` 或打开模型设置页。
- **行为**：`mode` 与持久化状态一致；real 模式但连接不可用时页面明确标注；切换前后无前后端状态漂移。
- **输出**：一致、诚实的状态展示。

## 非功能需求
- **诚实**：模式状态前后端一致；real 不可用时如实标注；不伪造切换成功。
- **可靠**：切换是持久化操作，重启后保持；切换失败不产生半状态。
- **性能**：切换为本地库写入 + 配置重载，秒级生效。
- **安全**：模式切换不涉及凭据读写；与既有 Key 加密纪律一致。

## 数据与接口影响
- 数据：新增模式持久化（应用库键值或既有配置表扩展），涉及数据库迁移（若需）。
- 接口：`GET /model/config` 返回切换后模式；可能新增 `PUT /model/mode`（或等价）写接口；既有结构兼容。

## 验收标准
- [ ] AC1: 当运维在模型设置页把模式从 mock 切到 real 并保存时，`GET /model/config` 应返回 `mode=real`，会话链路按 real 运行。
- [ ] AC2: 当从 real 切回 mock 时，`GET /model/config` 应返回 `mode=mock`，会话链路按 mock 运行。
- [ ] AC3: 切换后重启后端，模式应保持上次设置（持久化生效）。
- [ ] AC4: 当 real 模式但未配置可用 Provider/API Key 时，保存应成功但页面如实提示"real 模式已保存但当前不可用"（不伪造切换已生效），会话链路应保持不可用/降级标注。
- [ ] AC5: `GET /model/config` 的 `mode` 与页面展示应始终一致，无前后端漂移。
- [ ] AC6: 模式切换接口与响应不得包含 API Key 明文、完整 DSN 或 `sk-` 内容。
- [ ] AC7: 回归 —— 既有 `test_model_config_api.py`、`test_model_provider_api.py`、`test_agent_gateway.py` 相关全绿；前端 `typecheck`/`test`/`build` 通过。

## 边界与约束
- 安全边界：模式切换不读写凭据；接口脱敏纪律不变。
- 降级策略：real 无可用 Provider → 诚实降级 mock 或标注不可用；持久化失败 → 返回错误不产生半状态。
- 兼容性：`OPERMIND_API_KEY` env 仍是兜底事实；DB 激活 Provider 优先机制不变；既有接口契约兼容。

## 完成定义（DoD）
- [ ] 全部 AC（AC1–AC7）通过
- [ ] 相关回归测试全绿
- [ ] `git status` 只出现本 PRD 允许的文件
- [ ] 模式持久化迁移执行成功（若涉及）
- [ ] 接口与页面均不含 API Key / 凭据明文
- [ ] 前端 `typecheck` / `test` / `build` 通过

## 开放问题
1. **模式持久化位置**：应用库简单键值表，还是复用既有配置/Provider 表？→ 执行期 Design 定。
2. **real 模式的"可用 Provider"判定**：当前 `GET /model/config` 已有 `judge_model`/`diagnostic_model` 结构，切 real 时如何判定"可用"？→ 推荐复用 `has_api_key` + 验证状态，执行期细化。
3. **env 兜底语义**：用户切了模式后，env 里的 `OPERMIND_API_KEY` 是否仍生效？→ 推荐：运行时模式优先，env 只是"从未切过"时的默认。

## GitHub Issue（已确认后回填）
- issue：#55（https://github.com/wzhwwwzzzhhh/oper-mind/issues/55）
- 状态同步：issue 状态与 PRD 状态一致（已确认=open，完成=closed）；中间过程留在 workpack。
