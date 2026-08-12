---
title: 模型调用参数暴露——temperature 等运行参数的受控配置
status: 已确认
domain: model
phase: P8
issue: 66
updated: 2026-08-12
---

# 模型调用参数暴露——temperature 等运行参数的受控配置 · PRD

## 背景

模型设置页当前没有**模型运行参数**的配置能力（`docs/接口清单.md` 第四大模块"缺少"表："模型参数（temperature / max_tokens 等）……若确需暴露，得先定哪些参数真进 Agent 调用链"）。原先页面上有 7 个只写 localStorage 的假开关，已按 `完善清单.md` P1-7 删除——不复活本地假状态，参数必须真进调用链才算配置。

现状：后端 `backend/src/core/llm.py` 的 `LLMClient.chat()` 只暴露 `temperature`（固定默认 0.0，为实验可复现），`max_tokens` / `top_p` 等未暴露。参数在代码里写死，运维无法从界面调整。

关联：`docs/接口清单.md`（第四大模块缺表）、`docs/prd/model/P4.3-model-settings-real.md`（明确排除模型参数暴露）、`docs/prd/model/P6-model-provider-key-management.md`（Provider/Key 管理已落地）、`docs/完善清单.md` P1-7（删假开关）、`docs/产品定义.md`（用户模型 Provider 设置属平台能力）。

## 目标

1. 运维能在模型设置页配置**真实进入 Agent 调用链**的模型参数（首版 temperature，可选 max_tokens）。
2. 参数持久化、按 Provider 或全局生效（Design 定作用域），变更即时生效。
3. 配置诚实——参数真进调用链，非 localStorage 假状态；未配置时用后端默认。

## 用户故事

作为运维工程师，我想在模型设置页调整诊断模型的 `temperature`（比如降低随机性），保存后会话链路立刻按新值调用——而不是改代码或接受固定 0.0。

## 范围

### 做什么
- 模型参数配置：前端模型设置页新增参数表单（首版 `temperature`，`max_tokens` 视 Design）。
- 持久化：参数存后端（应用库键值，对齐 `app_settings` 既有模式或 Provider 表扩展，Design 定），非 localStorage。
- 生效链路：会话链路读取配置参数传给 `LLMClient.chat()`，替换写死的默认值；未配置用后端默认。
- 诚实标注：配置前后端一致；未配置显示默认值。

### 不做什么（明确排除）
- 不做未进调用链的参数暴露（`top_p` / `frequency_penalty` 等如不进 `chat()`，则不暴露）。
- 不做多模型路由策略（按 Agent 角色分配参数，`docs/产品定义.md` §7 未决）。
- 不做参数的作用域矩阵（每个 Agent 独立参数）——首版全局或按 Provider，Design 定。
- 不做用量/成本统计（另写 PRD）。
- 不复活 localStorage 假开关（`完善清单.md` P1-7 已删）。
- 不改变 mock 模式行为（mock 不调真实 API，参数仅对 real 生效）。

## 功能需求

### 1. 模型参数配置
- **输入**：模型设置页的参数表单（`temperature` 等）。
- **行为**：
  - 参数写入后端持久化（应用库键值或 Provider 表扩展，Design 定）。
  - 校验参数合法（如 `temperature` ∈ [0, 2]，`max_tokens` ≥ 1）。
  - 变更后会话链路按新参数调用。
- **输出**：参数已保存；`GET /model/config`（或等价）返回当前参数。

### 2. 生效链路
- **输入**：会话/调查发起。
- **行为**：`LLMClient` 读取配置的默认参数（当前 `chat()` 的 `temperature` 默认 0.0 写死，改为读取配置），未配置时仍用 0.0。现有调用点大多走默认值，无需逐个改调用点；显式传参处（graph.py 两处 `temperature=0.0`）保持显式值不变（Design 定是否改）。
- **输出**：会话链路按配置参数运行。

### 3. 诚实标注
- **输入**：模型设置页 / 配置读取。
- **行为**：参数状态前后端一致；未配置显示默认值并标注；非法输入被拒。
- **输出**：一致的配置展示。

## 非功能需求
- **诚实**：参数真进调用链；未配置显示默认值；不伪造"已配置"。
- **可靠**：参数持久化，重启后保持；校验非法输入。
- **安全**：参数配置不涉及凭据；接口脱敏纪律不变。
- **性能**：参数读取为本地库读取，ms 级。

## 数据与接口影响
- 数据：新增参数持久化（应用库键值或 Provider 表扩展），涉及数据库迁移（若需）。
- 接口：`GET /model/config`（或等价）返回参数；可能新增 `PUT /model/params`（或等价）写接口；既有结构兼容。

## 验收标准
- [ ] AC1: 当运维保存 `temperature=0.5` 时，会话链路的 `LLMClient.chat()` 应传 `temperature=0.5`（真进调用链，非 localStorage）。
- [ ] AC2: 当未配置参数时，应使用后端默认值（temperature 0.0）并如实标注。
- [ ] AC3: 当参数非法（temperature 超范围）时，应拒绝保存并返回明确错误。
- [ ] AC4: 参数持久化，重启后保持上次设置。
- [ ] AC5: 配置前后端一致（页面展示 = 后端读取值）。
- [ ] AC6: 参数配置接口与响应不得包含 API Key 明文、完整 DSN 或 `sk-` 内容。
- [ ] AC7: 未被允许暴露的参数（如未进 `chat()` 的 top_p）不得出现在配置界面。
- [ ] AC8: mock 模式行为不变（mock 不调真实 API，参数不影响 mock 路径；配置仅对 real 调用生效）。
- [ ] AC9: 回归 —— 既有 `test_model_config_api.py` / `test_model_provider_api.py` / `test_agent_gateway.py` 相关全绿；前端 `typecheck`/`test`/`build` 通过。

## 边界与约束
- 安全边界：参数配置不读写凭据；接口脱敏纪律不变。
- 降级策略：未配置 → 后端默认；持久化失败 → 返回错误不产生半状态；mock 模式参数不生效。
- 兼容性：既有 `GET /model/config` 契约兼容；未配置时行为与现状一致。

## 完成定义（DoD）
- [ ] 全部 AC（AC1–AC9）通过
- [ ] 相关回归测试全绿
- [ ] `git status` 只出现本 PRD 允许的文件
- [ ] 参数持久化迁移执行成功（若涉及）
- [ ] 参数配置接口与页面均不含凭据明文
- [ ] 前端 `typecheck` / `test` / `build` 通过

## 开放问题
1. **暴露哪些参数**：首版只 `temperature`，还是加 `max_tokens`？→ 推荐首版 temperature + max_tokens（两者都进 `chat()`），Design 定。
2. **参数作用域**：全局生效，还是按 Provider？→ 推荐全局（简单），按 Provider 后续。Design 定。
3. **是否影响 mock 评测**：mock 不调真实 API，参数不生效——是否需要在 mock 场景也暴露配置但标注"仅 real 生效"？→ Design 定。

## GitHub Issue（已确认后回填）
- issue：#66（https://github.com/wzhwwwzzzhhh/oper-mind/issues/66）
- 状态同步：issue 状态与 PRD 状态一致（已确认=open，完成=closed）；中间过程留在 workpack。
