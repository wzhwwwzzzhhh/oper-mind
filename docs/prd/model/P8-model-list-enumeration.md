---
title: 模型可用列表探测——Provider 侧模型枚举
status: 完成
domain: model
phase: P8
issue: 63
updated: 2026-08-12
---

# 模型可用列表探测——Provider 侧模型枚举 · PRD

## 背景

模型设置页当前模型名**全靠手填**（`docs/接口清单.md` 第四大模块"缺少"表：`Provider 下可用模型列表`，影响"模型名得手填，填错要等 verify 或真实调用才报错"）。P4.3（`docs/prd/model/P4.3-model-settings-real.md`）与 P6（`docs/prd/model/P6-model-provider-key-management.md`）都明确排除了"模型列表自动发现（Ollama 等 Provider 的模型枚举）"——本 PRD 是这两个的后继：把 Provider 侧可用的模型列表拉进前端，减少手填错误。

P6 已落地：Provider 配置（Base URL / 模型 / API Key）AES-256-GCM 加密落库、`verify` 连通性校验、DB 激活 Provider 优先。OpenAI-compatible Provider 的标准能力是 `GET /v1/models`（返回可用模型名列表）。本 PRD 复用既有连接与脱敏纪律，新增只读模型枚举。

现状缺口：运维在模型设置页新建 Provider 时，模型名要么手填（易错），要么跳过等 verify 报错。若能枚举 Provider 侧模型，选择即正确。

关联：`docs/接口清单.md`（第四大模块缺表）、`docs/prd/model/P4.3-model-settings-real.md`（明确排除模型列表自动发现）、`docs/prd/model/P6-model-provider-key-management.md`（加密 Key + verify 已落地）、`docs/prd/model/P8-model-mode-switch.md`（同批 P8，运行时模式切换）、`docs/产品定义.md`（用户模型 Provider 设置属平台能力）。

## 目标

1. 运维在模型设置页新建/编辑 Provider 时，能**拉取该 Provider 的可用模型列表**并选择，无需手填。
2. 模型枚举为**受控只读**探测（限时、脱敏、失败诚实标注），与 `verify` 同纪律。
3. 未启用枚举能力的 Provider 如实标注，不伪造模型列表。

## 用户故事

作为运维工程师，我在模型设置页接入一个 OpenAI-compatible Provider 时，应能点击"刷新模型列表"看到该 Provider 实际可用的模型名并选择——而不是手填一个可能不存在的名字等调用时报错。

## 范围

### 做什么
- Provider 侧模型枚举接口：`GET /model/providers/{provider_id}/models`（或等价），读取该 Provider 可用模型名列表。
- 复用既有连接与脱敏纪律：受控 HTTP 请求 `GET /v1/models`，限时、失败诚实标注、不暴露响应体/凭据。
- 前端模型设置页：新建/编辑 Provider 时提供"刷新模型列表"按钮，展示模型下拉供选择。

### 不做什么（明确排除）
- 不做模型参数（temperature / max_tokens）暴露（接口清单欠账，另行排期）。
- 不做用量/成本统计（接口清单欠账，另行排期）。
- 不做多模型路由策略（按 Agent 角色分配，`docs/产品定义.md` §7 未决）。
- 不把模型列表缓存/持久化（每次请求现场拉取，或仅限时缓存，Design 定）。
- 不接入非 OpenAI-compatible 的模型枚举协议（Ollama 原生 `/api/tags` 等，按 Provider 类型分支，首版只做 OpenAI-compatible `GET /v1/models`）。
- 不暴露 API Key、完整 Base URL、`sk-` 或响应体原文。

## 功能需求

### 1. Provider 侧模型枚举（GET /model/providers/{provider_id}/models）
- **输入**：Provider ID。
- **行为**：
  - 使用该 Provider 已保存的 Base URL + API Key，发起受控 `GET /v1/models`（限时，复用 P6 连接验证客户端）。
  - 解析返回的模型名列表（受控、限长、去重）。
  - 连接失败/超时/无权限 → 返回明确错误状态与安全原因（不暴露响应体、异常或凭据）。
  - 未配置 Provider 或该 Provider 不支持模型枚举 → 诚实标注"不可用/未启用"。
- **输出**：可用模型名列表（或失败/不可用状态）。

### 2. 前端模型选择
- **输入**：模型设置页新建/编辑 Provider 表单。
- **行为**：提供"刷新模型列表"按钮；拉取成功后展示模型下拉供选择；失败展示安全原因；未配置时展示"未启用"。
- **输出**：模型选择下拉（或失败/未启用提示）。

## 非功能需求
- **安全**：模型枚举复用 P6 连接验证纪律——受控只读请求、限时、失败不暴露凭据/响应体；API Key 不进日志/Trace/响应。
- **诚实**：枚举失败/未启用如实标注，不伪造模型列表。
- **性能**：枚举限时（复用 P6 verify 的超时模式）；列表限长（如 100 条）。
- **可靠**：单个 Provider 枚举失败不影响其他 Provider。

## 数据与接口影响
- 数据：无新增持久化、无迁移（模型列表现场拉取，不落库）。
- 接口：新增 `GET /model/providers/{provider_id}/models`；既有 Provider 接口契约不变。

## 验收标准
- [ ] AC1: 当请求 `GET /model/providers/{provider_id}/models` 且该 Provider 可连通时，应返回可用模型名列表。
- [ ] AC2: 当 Provider 连接失败/超时时，应返回失败状态与安全原因，不暴露响应体、异常详情或凭据。
- [ ] AC3: 当 Provider 未配置或不支持模型枚举时，应诚实标注"不可用/未启用"，不伪造列表。
- [ ] AC4: 模型枚举响应不得包含 API Key 明文、完整 Base URL、`sk-` 或原始响应体。
- [ ] AC5: 前端模型设置页应提供"刷新模型列表"入口，成功展示模型下拉，失败展示安全原因，未配置展示"未启用"。
- [ ] AC6: 枚举请求限时（复用 P6 verify 超时），列表限长。
- [ ] AC7: 单个 Provider 枚举失败不影响其他 Provider。
- [ ] AC8: 回归 —— 既有 `test_model_provider_api.py`、`test_model_config_api.py`、`test_agent_gateway.py` 相关全绿；前端 `typecheck`/`test`/`build` 通过。

## 边界与约束
- 安全边界：受控只读探测；限时；失败不暴露凭据/响应体；凭据纪律与 P6 一致。
- 降级策略：连接失败 → 失败状态；未配置/不支持 → 未启用；不伪造模型列表。
- 兼容性：既有 Provider 接口契约不变；mock 模式行为一致；不新增凭据/迁移。

## 完成定义（DoD）
- [ ] 全部 AC（AC1–AC8）通过
- [ ] 相关回归测试全绿
- [ ] `git status` 只出现本 PRD 允许的文件
- [ ] 未新增持久化/迁移/凭据
- [ ] 模型枚举请求与响应均不含凭据/原始响应体
- [ ] 前端 `typecheck` / `test` / `build` 通过

## 开放问题
1. **模型列表是否缓存**：现场每次拉取，还是短时缓存（TTL）？→ 推荐短时缓存（避免每次编辑都打 Provider），Design 定。
2. **非 OpenAI-compatible Provider 的枚举**：Ollama `/api/tags` 等是否首版支持，还是只做 OpenAI-compatible？→ 推荐首版只做 OpenAI-compatible，其余按类型分支后续加。

## GitHub Issue（已确认后回填）
- issue：#63（https://github.com/wzhwwwzzzhhh/oper-mind/issues/63）
- 状态同步：issue 状态与 PRD 状态一致（已确认=open，完成=closed）；中间过程留在 workpack。
