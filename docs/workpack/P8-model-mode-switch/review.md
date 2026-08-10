# P8-model-mode-switch · 独立审查

> 审查方式：readonly 子代理（general）只读 diff 与文档，未运行测试/迁移/写文件。
> 审查输入：plan.md、evidence.md、当前 PRD（进行中）、已确认 Design、基线文档、`git diff main..HEAD`。
> 审查日期：2026-08-10

## 总体：PASS（无 P0/P1）

## 发现

- [P2] 可测性（已修）：`MODEL_MODE_PERSISTENCE_FAILED` → 500 映射实现正确但无自动化用例。→ 已补 `test_model_mode_api.py::test_持久化失败返回500且不产生半状态`。
- [P2] 可测性（已修）：AC1/AC2 会话链路生效点仅有 `resolve_runtime_mode` 单测间接支撑，无直接断言。→ 已补 `test_model_mode_resolver.py::test_会话链路按生效模式构造LLM`（LLM client.api_key + mock 场景激活断言）。
- [P3] 风格（已修）：`model_providers.py` 文件头被写入 UTF-8 BOM。→ 已去除。
- [P3] 风格（已修）：`_load_secret_key_or_none` 在 routes.py 重复定义；`_model_provider_service` 内联重复加载。→ routes.py 内复用同一助手，消内部重复。
- [P3] 死代码（已修）：`SqlAlchemyAppSettingsRepository.delete()` 与 `ModelModeApplicationService.get_mode()` 无调用方。→ 已删除。
- [P3] 语义重载（design 内一致，未改）：应用库降级路径下 `mode_available=True` 也携带 reason；页面仅在 `real && !mode_available` 展示，D1 语义已明确定义。
- [P3] `/health` 残缺口（design 内一致，未改）：持久化 real 无 Key 时 `/health` 返回 `mode=real`，与 `GET /model/config` 一致但未暴露 `mode_available`；Design 已定语义。

## AC 证据表（子代理初评 + 修后补充）

- AC1: PASS —— resolver `test_运行时切到real且env有Key时可用`；API `test_切换到real返回新模式`；修后补 `test_会话链路按生效模式构造LLM`（real 分支）。
- AC2: PASS —— resolver `test_运行时切到mock覆盖env真实Key`；修后补 `test_会话链路按生效模式构造LLM`（mock 分支：client.api_key=mock + S1 激活）。
- AC3: PASS —— `test_切换后重启保持`（新 session 工厂读回 real/runtime）。
- AC4: PASS —— resolver `test_运行时切到real但无可用Key时诚实降级`；API `test_real无可用Key时保存成功但如实标注不可用`；前端 `ModelSettingsPage.test.tsx` 两用例。
- AC5: PASS —— API `test_切换后GET与页面状态一致`（PUT 返回值 == 随后 GET）；前端 `setQueryData` + `useEffect` 同步。
- AC6: PASS —— API `test_切换接口不暴露凭据`（无 `sk-`/api_key/DSN 明文）。
- AC7: PASS —— `test_model_config_api.py`/`test_api.py`/迁移测试同步新字段；`test_agent_gateway.py` 黑盒回归无需改动；修后 `pytest tests -q` → 359 passed、mypy no issues、ruff clean、前端 typecheck/test/build 全绿。

## 结论：PASS

无 P0（无凭据泄露/未授权写/mock 冒充真实——降级统一 `mode_available=false`+原因，应用库不可用回退 env 且永不 raise）。
无 P1（范围对齐：34 个改动文件均在 plan 改动面内；契约加法扩展、PUT 幂等/422/500 映射、三处 `resolve_runtime_mode` 一致性、跨层 TypedDict、`transaction.py` 无跨模块私有导入）。
两项 P2 已按加固建议补测试后合入。
