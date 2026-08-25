# P8-judge-runtime-truthfulness · 审查记录（review）

> 独立审查类型：架构审查（arch-review）+ 实现独立 Review（dev-execute Phase 4）
> 审查日期：2026-08-27

## 1. arch-review（设计闸门）

- **审查对象**：`docs/design/agent-runtime/P8Judge运行时真实性与配置面收口Design.md`（草稿版）
- **方式**：独立只读子代理，写审分离
- **结论**：**PASS**（无 P0/P1）
- 关键核实（全仓 grep）：
  - `fallback.py` 唯一引用确为 `tests/test_diagnosis.py`（随删合理）；
  - `_mock_response` 确为零引用（现行 mock 走 `_mock_chat`）；
  - `require_judge_llm` 确无 `True` 调用点；
  - `GET /model/config` 的 `judge_model` 字段结构确在 `schemas.py:68` 完整保留；
  - 删 env 映射 / judge_model 恒 None / activate 拒 judge 与 PRD 硬约束（不删字段、不迁移、不改编排）不冲突。
- **P2/P3 发现与处理**：
  - [P2] activate 对 judge 400 伴随新公开错误码 `JUDGE_ENDPOINT_NOT_ENABLED` → 已并入 Design §6 用户确认项（已确认）。
  - [P2] `GET /model/providers` 存量 judge 行仍字面返回 `active_endpoint='judge'` → Design 新增 D7：公开投影值收口为 null（未启用），并实现于 `resources.provider_resource`。
  - [P3] `model_runtime_mode.py:20`、`config.py:81` docstring 遗漏 → 均已同步更新。
- 用户确认（2026-08-27）：收口范围为"展示 + 消费 + 激活全面收口为未启用，公开类型与 DB 结构完整保留"；存量 judge 行保留但投影为未启用。

## 2. 实现独立 Review（dev-execute Phase 4）

- **审查对象**：`feat/P8-judge-runtime-truthfulness` 分支实现（后端 + 前端 + 文档）；
  基线 origin/main=d299661（审期间 #106 合入，已并入分支并核实无 #103 回退混入）
- **检查项**
  - 后端：`config.py` 删 `OPERMIND_JUDGE_*` env 映射与 `require_judge_llm` 参数；`errors.py` 新增 `JudgeEndpointNotEnabledError`；`model_providers.activate` 拒 judge（400）、`resolve_model_config` 删 judge 叠加；`routes._model_config_resource` judge_model 恒 None + 错误码 400 登记；`resources.provider_resource` judge 值收口；`app.py` 健康回退删 judge_llm；删 `core/fallback.py` + `tests/test_diagnosis.py` + `llm._mock_response`；更新 debate/reflection/dependencies/model_runtime_mode 注释。
  - 前端：删"裁判模型"卡片、"设为裁判"按钮、"裁判生效"标签；judge 显示为"未启用"；新增"质量复核（Debate / Reflection）由主诊断模型承担"说明；测试同步（`ModelSettingsPage.test.tsx`、`App.test.tsx`）。
  - 契约核对：`GET /model/config` 字段结构不变（judge_model 保留）、`active_endpoint`/`endpoint` Literal 不变、无迁移无 DB 结构变更（`git diff --check` 干净）。
- **结论**：**PASS**（无 P0/P1）——PR diff 严格符合 PRD AC1–AC10 与 Design D1–D7（含 §6 已确认三项决策），
  无越界改动、无死代码残留、无 #103 回退、无凭据/CoT 进入公开面；仅少量 P2/P3 文档与样式瑕疵。
- P2/P3 处理：
  - [P2] 完善清单 P0 汇总行未随 P0-6 标 ✅ 同步 → 已修正（`6|未修1|在修2|已修3`，commit 0ada4bb）。
  - [P3] 完善清单头部更新日期 → 已补 2026-08-27（#104 收口记录）。
  - [P3] ModelSettingsPage 防御分支 `judge→'未启用'` 命中 sample 高亮样式 → 已改为返回 null
    （与后端投影语义一致，样式走 muted）。
  - [P3] 历史 Design（P8模型模式切换）中 judge_llm"展示-only"描述属历史文档，不在本工作包同步范围，不阻塞。
  - [P3] handlers.ts 未改（mock 已返回 judge_model:null，契约一致，Design 原文为"可选项"）。