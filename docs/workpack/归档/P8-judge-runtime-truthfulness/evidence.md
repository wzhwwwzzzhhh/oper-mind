# P8-judge-runtime-truthfulness · AC 证据表（evidence）

> 交付日期：2026-08-27｜分支：`feat/P8-judge-runtime-truthfulness`
> 验证实测：后端 `pytest tests -q` **605 passed**（4m51s）；前端 `typecheck` ✅、`test` **198 passed**（20 files）、`build` ✅；`git diff --check` ✅
> 依据：PRD `docs/prd/agent-runtime/judge-runtime-truthfulness.md`（AC1–AC10）

| AC | 内容 | 证据 |
|---|---|---|
| AC1 | 模型设置页 / `/model/config` 不再展示"裁判生效"，并如实标注质量节点由主诊断模型承担 | 前端删"裁判模型"卡 / "设为裁判"按钮 / "裁判生效"标签（`ModelSettingsPage.tsx`），新增"质量复核（Debate / Reflection）由主诊断模型承担，不接入独立裁判模型"；前端测试 `ModelSettingsPage.test.tsx`、`App.test.tsx` 断言无裁判误导 + 有诚实说明 |
| AC2 | `/model/config` 契约字段结构不变；`judge_model` 只表达"未启用" | `routes._model_config_resource` 中 `judge_model` 恒为 None（`schemas.py:68` 字段保留）；`test_model_config_api.py` 断言即使设置 `OPERMIND_JUDGE_*` env 也恒 None |
| AC3 | `core/fallback.py` 与 `llm.py:_mock_response` 已清理 | 两文件已删除（`fallback.py` 连同唯一引用 `tests/test_diagnosis.py`）；全仓 grep 复核零残留 |
| AC4 | 过时注释已更新（如 dependencies.py"审批执行器仍为空骨架"） | `api/v1/dependencies.py` 模块 + `build_v1_services_for_runtime` docstring 改为"已实现为受控动作执行器"；debate/reflection"简化实现"→"由主诊断模型承担"；`config.py`、`model_runtime_mode.py` docstring 更新 |
| AC5 | 质量节点由主诊断模型承担的驱动来源如实标注 | 模型页"运行边界"如实说明；无任何"已由独立裁判复核"语义；编排语义未变（debate/reflection 仍用主 llm） |
| AC6 | Trace/结果/日志无 CoT/Prompt/原始输出/原始 SQL/凭据 | 本次改动不新增 Trace 投影；`test_模型配置接口返回安全的诊断配置且裁判恒未启用` 断言 `judge-secret`/完整 URL/`api_key`/`sk-` 不出现 |
| AC7 | DB/Server/Log/Knowledge 工具边界与 #98/#99 白名单不变，质量节点行为回归通过 | 未改动 Agent/Tool/Gateway；后端全量 pytest 通过（mock 决定性、未执行状态如实场景回归） |
| AC8 | 未新增公开 API / 迁移 / Connector / 真实外部访问 / 高风险动作 | `git diff` 无迁移、无 schema 字段增删、无新端点；`active_endpoint`/`endpoint` Literal 与 DB 约束未动 |
| AC9 | 后端回归测试 + 前端 typecheck/test/build 通过；完善清单/跑通验证按实测更新 | 后端全量 pytest **605 passed** ✅；前端 `typecheck` ✅、`test` 198/198 ✅、`build` ✅；`git diff --check` ✅；`docs/完善清单.md` P0-6 ✅、`docs/跑通验证.md` C6 已记录 |
| AC10 | 路径 B 经 Design → Review → 用户确认后实施 | `arch-review` PASS（独立子代理）+ §6 三项决策用户确认（2026-08-27）+ 计划确认后实施 |
