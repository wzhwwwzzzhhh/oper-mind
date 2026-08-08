---
title: 模型 Provider 与 API Key 管理
status: 完成
domain: model
phase: P6
issue: 22
updated: 2026-08-07
---

# 模型 Provider 与 API Key 管理 · PRD

## 背景

模型设置目前**只读展示真实生效配置**（P4.3 已完成）：`GET /model/config` 返回当前生效的诊断/裁判模型安全视图（provider/base_url 主机/model、mock/real 模式），不含 API Key。但**没有 API Key 输入、Provider 切换或配置生效能力**——凭据只能靠运维直接改环境变量/`config.local.yaml`，前端无法操作。

现状缺口：产品定义将"用户模型 Provider 与 API Key 设置"列为平台能力（路线图第四阶段）；运维希望在前端配置/切换模型 Provider 并接入自己的 API Key，而不是改环境变量重启。当前无此能力，属明确未启用。

关联：`docs/prd/model/P4.3-model-settings-real.md`（已确认，只读展示，明确"不新增 API Key 输入/保存能力，须另行 PRD"）、`docs/产品定义.md`（用户模型 Provider 与 API Key 设置）、`docs/路线图.md`（第四阶段）、`docs/开发规范.md`（凭据只走环境变量、不得落库）、`docs/design/`（凭据方案，需 Design）。

## 目标

1. 运维能在前端配置模型 Provider（选择/切换 Provider 与模型），并输入自己的 API Key。
2. API Key 安全持久化，绝不落库明文；运行期连接状态可验证。
3. 配置变更即时生效（或经明确的重载机制），与当前只读展示一致。

## 用户故事

作为运维工程师，我接入自己的大模型服务时，应在模型设置页输入 Provider 的 Base URL 与 API Key、选择模型并验证连通，系统保存后会话链路使用我配置的模型——而不是要求我改环境变量重启。

## 范围

### 做什么
- 模型 Provider 配置：前端可新增/切换 Provider（Base URL / 模型 / 关联 API Key）。
- API Key 安全持久化：加密保存或外部密钥引用（方案待 Design），绝不落明文；界面掩码展示、不回显。
- 连接验证：保存时测试 Provider 连通（受控、限时），失败诚实标注。
- 配置生效：变更后的配置进入会话链路（诊断/裁判模型），mock/real 模式如实标注。

### 不做什么（明确排除）
- 不做多租户 / 多用户的模型权限管理（后续阶段）。
- 不做模型列表自动发现（Ollama 等 Provider 的模型枚举）。
- 不做 Agent 调用策略开关的真实化（沿用 P4.3 结论，保留前端本地偏好或只读）。
- 不改后端配置加载机制本身（`load_config()` 内部 env 优先 YAML 的既有逻辑）。**经 arch-review 决议（用户 2026-08-06 拍板）：模型端点生效配置由 DB 激活的 Provider 承担，未激活时 env/YAML 兜底**；详见 `docs/design/model/P6模型Provider与APIKey管理Design.md`。
- 不接外部密钥服务（Vault 等，后续阶段）。

## 功能需求

### 1. Provider 配置与 API Key 安全保存
- **输入**：Provider 配置（名称 / Base URL / 模型）与 API Key。
- **行为**：API Key 经安全方案持久化（**已决议：AES-256-GCM 加密落库，主密钥 `OPERMIND_SECRET_KEY` 走 env**，见 `docs/design/model/P6模型Provider与APIKey管理Design.md`），界面掩码展示、不落明文、不进日志/Trace/接口响应；Base URL 与模型可编辑。
- **输出**：Provider 配置保存成功；API Key 掩码展示。

### 2. 连接验证
- **输入**：保存时触发连接测试。
- **行为**：受控、限时测试 Provider 连通性（只发最小验证请求，不执行任意调用）；失败诚实标注原因（不暴露响应体/凭据）。
- **输出**：连接状态（成功 / 失败原因）。

### 3. 配置生效与诚实标注
- **输入**：已保存的 Provider 配置。
- **行为**：会话链路使用当前生效配置的诊断/裁判模型；未配置/不可用如实标注；mock/real 模式一致。
- **输出**：会话链路按生效配置运行；模型设置页展示生效状态。

## 非功能需求
- **安全**：API Key 绝不落库明文；掩码展示；不进日志/Trace/响应；只读回显安全视图（对齐 P4.3）。
- **可靠**：连接验证限时；Provider 不可用不影响其他 Provider。
- **诚实**：未配置/不可用/验证失败如实标注，不伪造连接成功。

## 数据与接口影响
- 数据：新增 API Key 安全持久化方案（**已决议：AES-256-GCM 加密落应用库专用表，主密钥 `OPERMIND_SECRET_KEY` 走 env**，涉及 `model_providers` 表迁移）。
- 接口：新增模型 Provider 配置的读写接口（保存/验证/列表/激活/删除）；P4.3 只读接口结构保持兼容。

## 验收标准
- [ ] AC1: 当运维在前端新增 Provider 并保存 API Key 时，配置应安全保存，API Key 掩码展示，不落明文。
- [ ] AC2: 当读取已保存 Provider 配置时，接口响应不得包含 API Key 明文（掩码或隐藏）。
- [ ] AC3: 当保存触发连接验证且 Provider 可连通时，应返回连接成功。
- [ ] AC4: 当 Provider 连接失败/超时时，应返回失败状态与安全原因，不暴露响应体/凭据。
- [ ] AC5: 当会话链路使用已配置的 Provider 时，应使用生效配置的诊断/裁判模型运行。
- [ ] AC6: 当未配置 API Key 时，会话链路应诚实降级（mock 或提示未配置），不伪造真实连接。
- [ ] AC7: 变更 Provider 配置后，会话链路应使用新配置（或经明确重载生效），mock/real 模式如实标注。
- [ ] AC8: 回归 —— `test_model_settings` 相关、`test_agent_gateway.py` 全绿；前端 `typecheck`/`test`/`build` 通过。
- [ ] AC9: 日志、Trace、接口响应、前端状态中不得出现 API Key 明文。

## 边界与约束
- 安全边界：API Key 绝不落明文；掩码；只读安全视图回显；无凭据进日志/Trace/响应。
- 降级策略：未配置 → 诚实空态；连接失败 → 失败状态；Provider 不可用不影响其他。
- 兼容性：P4.3 只读接口契约兼容；mock/real 模式如实标注；Agent 调用策略保留 P4.3 结论。

## 完成定义（DoD）
- [ ] 全部 AC（AC1–AC9）通过
- [ ] 相关回归测试全绿
- [ ] `git status` 只出现本 PRD 允许的文件
- [ ] API Key 无明文落库/日志/Trace/响应/截图
- [ ] 连接验证只发最小验证请求，不做任意调用

## 开放问题（已由 Design 决议，用户 2026-08-06 拍板）
1. **API Key 持久化方案**：AES-256-GCM **加密落库**（应用库专用表），主密钥 `OPERMIND_SECRET_KEY` 走环境变量（≥32 字符），明文永不落库；外部密钥服务（Vault）不做。→ 已定，见 `docs/design/model/P6模型Provider与APIKey管理Design.md` D1。
2. **配置生效方式**：DB 激活配置**优先于** env/YAML（未激活时兜底），每 Run 解析构造 LLM 客户端，**保存即生效、无需重启**；mock/real 如实标注。→ 已定，见 Design D2；PRD 排除项已同步放宽。
3. **Provider 列表范围**：**任意 OpenAI-compatible Base URL**（自由输入，http(s) + 主机解析校验，非 localhost 强制 https、拒私有/保留段），不做硬编码白名单；常见 Provider 仅 UI 提示。→ 已定，见 Design D3。

## GitHub Issue（已确认后回填）
- issue：#22，指向本 PRD 的 GitHub issue（https://github.com/wzhwwwzzzhhh/oper-mind/issues/22）
- 状态同步：issue 状态与 PRD 状态一致（已确认=open，完成=closed）；中间过程留在 workpack。
