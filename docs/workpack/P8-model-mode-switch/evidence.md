# P8-model-mode-switch · AC 证据表

> 按切片逐步回写；每条 AC 标注证据（测试命令输出 / 文件 / 提交）与状态。

## S1 模式持久化 + 生效解析层 + 会话链路生效

| AC | 证据 | 状态 |
|---|---|---|
| AC1（mock→real 切换后生效） | `tests/test_model_mode_resolver.py::test_运行时切到real且env有Key时可用`（mode=real, source=runtime, available） | ✅ |
| AC2（real→mock 切换后生效） | `tests/test_model_mode_resolver.py::test_运行时切到mock覆盖env真实Key`（mode=mock, source=runtime, config llm api_key=mock） | ✅ |
| AC3（重启后模式保持） | `tests/test_model_mode_resolver.py::test_切换后重启保持`（新会话工厂读取仍保持 real） | ✅ |
| AC7（后端部分回归） | `pytest tests -q` → 350 passed；mypy → no issues；ruff → All checks passed | ✅ |

## S2 公开 API + 前端切换

| AC | 证据 | 状态 |
|---|---|---|
| AC4（real 无可用 Key 如实标注） | `test_model_mode_api.py::test_real无可用Key时保存成功但如实标注不可用`（PUT real 成功 + `mode_available=false` + 原因）；前端 `ModelSettingsPage.test.tsx::切换到 real 保存后如实提示不可用` | ✅ |
| AC5（GET/页面一致无漂移） | `test_model_mode_api.py::test_切换后GET与页面状态一致`（PUT 返回值 == 随后 GET）；前端 `useEffect` 同步 mode_selection + `setQueryData` 缓存 | ✅ |
| AC6（切换接口无凭据） | `test_model_mode_api.py::test_切换接口不暴露凭据`（无 `sk-` / api_key / DSN 明文） | ✅ |
| AC7（回归） | `pytest tests -q` → 357 passed；mypy → no issues；ruff → All checks passed；前端 `typecheck`/`test`（99 passed）/`build` 通过 | ✅ |

## DoD 门禁

- [x] 迁移 upgrade/downgrade 成功（`app_settings` 表；手动 alembic upgrade head + downgrade 验证）
- [x] `git diff --check` 干净
- [x] 无凭据 / `sk-` / DSN 明文
- [x] `GET /model/config` 三字段加法扩展，既有字段未破坏
- [x] `PUT /model/mode` 幂等、无需 Idempotency-Key、持久化失败 → 500 并入既有错误映射
