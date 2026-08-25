# P8 Judge 运行时真实性与配置面收口 · Design

> 状态：已确认
> 更新：2026-08-27
> 关联：`docs/prd/agent-runtime/judge-runtime-truthfulness.md`（已确认，issue #104）、
> `docs/完善清单.md` P0-6 / P1-7、`docs/产品定义.md` §6/§7、
> `docs/开发规范.md` §7.2（配置面收口闸门）、`backend/src/config.py`、`backend/src/api/v1/routes.py`、
> `backend/src/application/model_providers.py`、`backend/src/domain/model_provider.py`、
> `frontend/src/features/models/ModelSettingsPage.tsx`

## 1. 目标与范围

**一句话目标**：消除"用户能在配置面/页面看到'裁判模型 / 裁判生效'，但 Debate / Reflection 质量节点从不使用
独立裁判"的诚实性缺口——把 judge 配置面收口为明确的"未启用"，同时清理相关死代码与过时注释。

### 做什么（对齐 PRD 路径 B）
- 后端不再"读入并声称已启用"任何独立裁判配置：env `OPERMIND_JUDGE_*` 消费下线、DB `judge` 激活 Provider
  不再叠加为生效配置、`GET /model/config` 的 `judge_model` 恒表达"未启用"。
- 前端模型设置页移除"裁判模型 / 设为裁判 / 裁判生效"误导展示，并如实说明质量节点由主诊断模型承担。
- 清理 `core/fallback.py`（RuleEngine）及唯一引用它的测试、`core/llm.py:_mock_response`；更新过时注释
  （`api/v1/dependencies.py`"审批执行器仍为空骨架"、`core/debate.py` / `core/reflection.py` "简化实现"）。

### 明确不做
- **不接线独立 Judge**（路径 A 不做）；不改变 Debate / Reflection 编排语义（仍用主诊断 `llm`）。
- 不改变 `GET /model/config` 契约**字段结构**（`judge_model` 字段保留，仅值表达"未启用"）。
- **不新增数据库迁移**；不修改 DB 约束 / 唯一约束；`active_endpoint` / `endpoint` 的公开 Literal 类型保留。
- 不新增公开 API、不新增 Connector / 服务类型 / 真实外部连接 / 高风险动作能力。
- 不改变 DB / Server / Log / Knowledge 工具边界与 P8 #98/#99 互斥角色白名单。

## 2. 设计决策

### D1 收口范围口径（本次 Design 定稿，交用户确认）
PRD 开放问题在"仅收展示层"与"连 env/Endpoint 一并下线"两者间选择。受 PRD 硬约束（不新增迁移、不改变
公开契约**结构**）限制，**"连 env/Endpoint 一并下线"只能做到"消费与引导面下线"，必须保留类型与 DB 结构**：

- env **消费**下线：可做，无契约影响。
- DB judge **叠加消费**下线：可做，仅内部接线。
- judge **激活入口**收口：可做（行为收口，不动 Literal / DB 约束）。
- `active_endpoint` / `endpoint` Literal、DB 约束：**保留**（移除需要迁移或改公开类型，违反硬约束）。

因此本 Design 采用"**展示 + 消费 + 激活 全面收口为未启用，公开类型与 DB 结构完整保留**"（即"连
env/Endpoint 一并下线"在硬约束内的最大可行落地），推荐给用户确认。备选"仅收展示层"作为保守选项，见 §6。

### D2 后端配置消费收口
- `src/config.py`：
  - 从 `_ENV_TO_CONFIG_KEY` **删除** `OPERMIND_JUDGE_API_KEY` / `OPERMIND_JUDGE_BASE_URL` / `OPERMIND_JUDGE_MODEL`
    三条映射（env 消费下线）。
  - `load_config(require_judge_llm=...)` 移除该参数（全仓无 `True` 调用点）及对应 `_require_llm_config(config, "judge_llm")`
    校验分支；`judge_llm` 键若仍残留于 YAML 仅作惰性数据，永不被消费 / 展示为生效。
- `src/application/model_providers.py#resolve_model_config`：删除 `("judge", "judge_llm")` 叠加分支，
  `config["judge_llm"]` 不再承载 DB 激活 Provider；docstring 同步更新（不再声称输出 `judge_llm` 生效段）。
- `src/api/v1/routes.py#_model_config_resource`：`judge_model` **恒为 `None`**（等价"未启用"），并加注释说明
  原因（无任何执行节点消费独立裁判，不再投影为已配置）。字段保留，契约结构不变 → PRD AC2。
- `backend/src/app.py#_env_config_fallback`：移除 `"judge_llm": {}` 键（健康检查回退不再兜 judge 字段）。

### D3 judge 激活入口收口
- `src/domain/model_provider.py` 的 `ProviderEndpoint.JUDGE` enum 值**保留**（公开类型不变）。
- `src/application/errors.py` 新增 `JudgeEndpointNotEnabledError`（`code="JUDGE_ENDPOINT_NOT_ENABLED"`，
  中文 message 如实说明"独立裁判模型未接入执行链，judge 端点未启用"）。
- `src/application/model_providers.py#ModelProviderApplicationService.activate`：命令入口先校验，凡
  `endpoint == ProviderEndpoint.JUDGE` 直接抛 `JudgeEndpointNotEnabledError`（400），不再接受新 judge 激活。
- `src/api/v1/routes.py`：`APPLICATION_ERROR_STATUS` 登记 `"JUDGE_ENDPOINT_NOT_ENABLED": 400`。
  该错误码为新增公开响应面增量（OpenAPI 未列错误码枚举，故无结构变化），经 arch-review 确认属 PRD
  "连 env/Endpoint 一并下线"委托范围，已并入 §6 用户确认。
- 已存在 `active_endpoint='judge'` 的存量行：保留（不迁移），但永不被叠加消费、永不被展示为"生效"。
  ——安全与诚实性：不产生"配置了却从未生效"的新死配置，也不动既有数据结构。

### D7 Provider 列表存量 judge 行的公开投影（arch-review P2 修正）
- `GET /model/providers` 的 `provider_resource` 投影中，`active_endpoint` 对 `ProviderEndpoint.JUDGE`
  **值收口为 `None`（未启用）**：DB 行保留 judge 值（不迁移、不清理），但公开投影一律表达"未启用"，
  避免 API 消费者把 judge 行误读为"已生效"；`ModelProviderResource.active_endpoint` 的 Literal 类型保留
  不变（契约结构不变）。前端因此天然显示"未启用"，无需再区分 judge 的生效文案。

### D4 前端展示收口（`frontend/src/features/models/ModelSettingsPage.tsx`）
- 删除摘要区"裁判模型"卡片（`judge`/`judge_model` 引用随之移除，`~:321`）。
- 删除 Provider 操作区"设为裁判"按钮（`~:444`）。
- `endpoint_label`：`judge` 不再返回"裁判生效"，改为诚实标签"裁判（未启用）"（`~:66`）；
  "当前会话链路使用"副标题仅在 `diagnostic` 时成立，`judge` → "独立裁判未接入执行链"。
- 新增诚实说明（放在"运行边界"节或摘要区）："质量复核（Debate / Reflection）由主诊断模型承担，
  不接入独立裁判模型。"
- `frontend/src/api/v1/client.ts`、`generated.ts`：类型 / 字段**不变**（后端 OpenAPI 未变）。

### D5 死代码与过时注释清理
- 删除 `backend/src/core/fallback.py`（`RuleEngine` / `analyze_with_fallback`），**并删除其唯一引用**
  `backend/tests/test_diagnosis.py`（该测试只测已删死模块；保留会引入 import 错误）。`app.py:_env_config_fallback`
  与 `_service_mode` 是"同名不同物"，不受影响。
- 删除 `backend/src/core/llm.py:_mock_response`（全仓零引用；现行 mock 走 `_mock_chat`）。
- 更新过时注释：
  - `backend/src/api/v1/dependencies.py` 模块 docstring 与 `build_v1_services_for_runtime` docstring：
    "审批执行器仍为空骨架，结构化字段保守留空" → 已实现受控动作执行器与风险字段接线的事实描述；
  - `backend/src/core/debate.py:47,53`、`reflection.py:77` "简化实现"注释 → "质量节点由主诊断模型承担"
    的如实说明（不再暗示将替换为独立裁判）。
- `config/config.example.yaml`：移除 `judge_llm` 示例段或改为"未启用，请勿配置"的注释，消除引导配置。

### D6 质量节点如实标注（PRD 功能需求 2 / AC5）
- 编排语义不变（Debate / Reflection 继续用主诊断 `llm`）；不新增独立裁判调用，避免成本 / 延迟。
- 公开面（模型设置页说明 + 现有 Trace 契约）只出现"质量节点由主诊断模型承担"，绝无"已由独立裁判复核"
  的虚假语义；Trace 不新增任何 judge / 裁判投影。

## 3. 文件改动面

### 后端（`backend/`）
| 文件 | 改动 |
|---|---|
| `src/config.py` | 删 `OPERMIND_JUDGE_*` env 映射；`load_config` 移除 `require_judge_llm` 参数与 judge 校验分支；docstring 同步（不再声称可要求独立裁判配置） |
| `src/application/errors.py` | 新增 `JudgeEndpointNotEnabledError` |
| `src/application/model_providers.py` | `resolve_model_config` 删 judge 叠加分支并更新 docstring；`activate` 拒 judge 激活 |
| `src/api/v1/routes.py` | `_model_config_resource` judge_model 恒 None；`APPLICATION_ERROR_STATUS` 加 400 登记；`provider_resource` 对 judge 值收口为 null（D7） |
| `src/app.py` | `_env_config_fallback` 移除 `"judge_llm": {}` |
| `src/domain/model_runtime_mode.py` | docstring 更新（不再声称 config 含 judge_llm 生效段，arch-review P3） |
| `src/core/fallback.py` | **删除**（死代码） |
| `src/core/llm.py` | 删除 `_mock_response` |
| `src/core/debate.py` / `reflection.py` | 更新"简化实现"注释为"由主诊断模型承担" |
| `src/api/v1/dependencies.py` | 更新"审批执行器仍为空骨架"过时注释 |
| `tests/test_diagnosis.py` | **删除**（仅测已删死模块） |
| `tests/test_model_config_api.py` | judge 相关断言改为"恒未启用 / 不受 env 影响" |
| `tests/test_model_provider_api.py` | 404 用例 endpoint 改 diagnostic；新增 judge 激活拒绝用例 |
| `tests/test_api.py` | `_env_config_fallback` 断言同步（移除 `judge_llm` 期望） |

### 前端（`frontend/`）
| 文件 | 改动 |
|---|---|
| `src/features/models/ModelSettingsPage.tsx` | 删裁判卡片 / 设为裁判按钮 / 裁判生效标签；judge 显示为未启用；新增诚实说明 |
| `src/features/models/ModelSettingsPage.test.tsx` | 同步展示断言；新增"无裁判误导 / 诚实说明"断言 |
| `src/test/handlers.ts` | 模型配置 mock 与 activate mock 保持契约一致（judge 激活 mock 返回拒绝可选项） |

### 配置 / 文档
| 文件 | 改动 |
|---|---|
| `config/config.example.yaml` | 移除 / 标注 `judge_llm` 段 |
| `docs/完善清单.md` | P0-6 按实测标 ✅（含日期与验证方式）；P1-7 关联收口记录 |
| `docs/跑通验证.md` | C3 及模型配置相关卡点按实测同步 |
| `docs/产品定义.md` | §6 已决策 / §7 未启用能力如实标注（新增一条：独立裁判未接入执行链） |
| `docs/路线图.md` | P8 完善项同步 |
| `docs/prd/agent-runtime/README.md` | 已含 judge PRD 索引（随交付确认） |
| `docs/workpack/P8-judge-runtime-truthfulness/` | plan / review / evidence（交付物） |

> **接口契约 / 迁移 / 数据库变更**：无公开 API 字段增删、无迁移、无 DB 结构变更。行为面唯一变化是
> `POST /model/providers/{id}/activate` 对 `endpoint=judge` 返回 400（原可激活），属本 PRD 收口范围。

## 4. 切片与验证（指引，不写死）
建议拆 3 片，每片独立可验收、互不阻塞：
1. **S1 展示层收口 + 诚实说明**（前端为主）：模型设置页不再出现裁判误导，质量节点说明如实。
2. **S2 后端配置面 / 激活收口 + 死代码清理**（后端为主）：judge_model 恒未启用、env / DB 消费下线、
   judge 激活拒绝、fallback.py / `_mock_response` / 过时注释清理。
3. **S3 文档与回归**：完善清单 / 跑通验证 / 产品定义 / 路线图同步；后端全量 pytest +
   前端 typecheck / test / build 全绿；`git diff --check` 干净。
各片验收语义均映射 PRD AC1–AC10；不含新增门禁项（无迁移、无公开 API）。

## 5. 风险、回滚与门禁
- **风险**：删 `fallback.py` 若遗漏引用会炸 import → 实施时先 `git grep` 全仓核对（已核对：唯一引用为
  `test_diagnosis.py`，随删）。`/model/config` `judge_model` 恒 None 可能被现存前端代码继续读取 →
  同步删前端裁判卡片读取路径，避免出现"undefined 回退"。
- **回滚**：本改动无迁移、无公开 API 结构变化，回滚 = 还原本次提交（撤销收口即可恢复旧展示/激活行为），
  存量数据不受影响。
- **门禁项**：配置面收口属 `docs/开发规范.md` §7.2 门禁 → 本 Design 经 arch-review PASS + 用户确认后方可实施。

## 6. 待用户确认的设计决策（2026-08-27 用户已确认）
1. **收口范围**：✅ 已确认"展示 + 消费 + 激活 全面收口为未启用，公开类型与 DB 结构完整保留"
   （即 PRD "连 env/Endpoint 一并下线"在硬约束内的最大可行落地）。备选"仅收展示层"不采纳。
2. **存量 judge 激活 Provider**：✅ 已确认保留行但永不被消费/展示为生效（D7 值收口为未启用，符合"不迁移"）。
3. **`activate` 对 judge 返回 400 拒绝**：✅ 已确认可接受（行为收口，OpenAPI 的 Literal 仍列 judge）；
   随之新增公开错误码 `JUDGE_ENDPOINT_NOT_ENABLED`（arch-review P2 要求单列，随本决策一并确认）。
