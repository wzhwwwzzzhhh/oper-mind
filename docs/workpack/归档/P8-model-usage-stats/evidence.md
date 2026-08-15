# P8-model-usage-stats · AC 证据表

> 验证记录随切片推进回写；证据先于断言（dev-execute 纪律）。

## S1 后端采集 + 统计接口

| AC | 证据 | 状态 |
|---|---|---|
| AC1 真实调用 usage 落库 | `backend/tests/test_usage_recording.py::test_真实调用后usage落库`（input/output/total + 模型名 + 时间戳）；`test_recorder真实落库与聚合查询`（SqlAlchemyUsageRecorder → model_usage_records 表可读回） | ✅ |
| AC2 GET /model/usage 聚合 | `backend/tests/test_model_usage_api.py::test_按模型聚合返回token与估算花费`（按模型分组聚合） | ✅ |
| AC3 时间窗过滤 | `test_时间窗过滤只返回窗口内`（10 天前记录被排除）；`test_from晚于to返回422`；`test_窗口跨度超过366天返回422` | ✅ |
| AC4 花费估算与标注 | `test_按模型聚合返回token与估算花费`（builtin 默认单价）；`test_配置单价后按配置估算`（configured）；`test_未列出模型回退通用默认并标注unset` | ✅ |
| AC5 mock 恒 0 | `test_mock调用不采集`；`test_mock模式统计为空态` | ✅ |
| AC6 空态 | `test_无记录返回空态`（HTTP 200 + items=[]） | ✅ |
| AC7 无内容/凭据 | `test_响应不含凭据与调用内容`（无 sk-/api_key/DSN/prompt）；表结构无内容字段 | ✅ |
| AC8 采集失败不阻断 | `test_采集失败不影响调用`（recorder 抛异常，chat 正常返回） | ✅ |
| 迁移 upgrade/downgrade | alembic upgrade head → downgrade -1 → upgrade head 均成功（见验证记录） | ✅ |
| ruff / mypy | `ruff check src tests` 全绿；mypy 9 个相关文件 0 错误 | ✅ |

## S2 前端用量展示

| AC | 证据 | 状态 |
|---|---|---|
| AC9 前端展示 + 时间窗 + 空态/失败态 | `ModelSettingsPage.test.tsx`：`展示用量统计聚合与估算标注`、`切换时间窗筛选后仍展示统计`、`用量统计读取失败时诚实提示`；空态文案「暂无用量记录。Mock 模式不采集用量」 | ✅ |
| AC10 回归 | 后端全量 pytest 结果见验证记录；前端 `typecheck` / `test`（ModelSettingsPage 17 通过）/ `build` 通过 | ✅ |

## 验证记录

- 后端聚焦：`pytest tests/test_usage_recording.py tests/test_model_usage_api.py tests/test_llm_client.py` → 24 passed
- 后端回归：`pytest tests/test_agent_gateway.py tests/test_model_provider_api.py tests/test_model_config_api.py tests/test_model_mode_api.py tests/test_model_params_api.py` → 70 passed
- 后端全量：`pytest tests -q` → **504 passed, 2 skipped**（0:07:23）
- 迁移：`alembic upgrade head` → `20260813_13_p8_model_usage (head)`；`downgrade -1` → 12；`upgrade head` → 13
- 前端：`npm run typecheck` 通过；`vitest run ModelSettingsPage.test.tsx` → 17 passed；`npm run build` 通过（5.89s）
- 门禁：`git diff --check` 干净（exit 0）
- 合 main：`git merge origin/main` 解冲突（dependencies.py / handlers.ts 各保留双方新增），合并后聚焦测试 52 passed；全量回归结果见上
- 迁移多头处理：main 并行 head（消息编辑 14 / 监控阈值 15）→ 本切片迁移接 15 后 + merge migration（`20260815_14_merge_p8_heads`）收敛唯一 head；`upgrade head` / `downgrade base` 验证通过；schema/迁移相关测试 30 passed
