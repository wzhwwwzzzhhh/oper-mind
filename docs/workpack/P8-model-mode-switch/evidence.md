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
| AC4 | （待 S2 回写） | ⏳ |
| AC5 | （待 S2 回写） | ⏳ |
| AC6 | （待 S2 回写） | ⏳ |
| AC7 | （待 S2 回写） | ⏳ |

## DoD 门禁

- [x] 迁移 upgrade/downgrade 成功（`app_settings` 表；手动 alembic upgrade head + downgrade -1 验证）
- [x] `git diff --check` 干净
- [x] 无凭据 / `sk-` / DSN 明文
