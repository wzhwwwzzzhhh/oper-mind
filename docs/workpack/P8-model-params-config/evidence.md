# P8-model-params-config · AC 证据表

## S1 参数持久化 + 解析层 + 读写 API（已完成）

验证记录：
- `pytest tests/test_model_params_api.py -q` → 20 passed（保存/清除/校验 422/边界值/幂等/重启持久/凭据/持久化失败/mock 独立）
- `pytest tests/test_model_config_api.py -q` → 4 passed（含新契约字段断言更新：params/params_defaults；脱敏断言精确化为 `token=secret`）
- `pytest tests/test_model_mode_api.py tests/test_model_mode_resolver.py tests/test_model_provider_api.py tests/test_model_provider_resolver.py -q` → 56 passed（回归）
- `git diff --check` 干净

| AC | 证据 | 状态 |
|---|---|---|
| AC2 | test_未配置时返回默认值并如实标注：params 全 None + params_defaults（0.0 / None） | PASS |
| AC1/AC5 | test_保存参数后GET与PUT一致：PUT 0.5/4096 → GET 相同 | PASS |
| AC4 | test_重启后参数保持：同一 SQLite 重建 runtime 仍返回配置值 | PASS |
| AC3 | test_非法参数返回422（6 组非法载荷）+ 边界值合法（0/2/1/102400） | PASS |
| AC6 | test_接口不暴露凭据：无 api_key / sk- / DSN | PASS |
| — | null=清除（test_清除单项恢复默认 / test_全部清除回到未配置） | PASS |
| — | 幂等：test_幂等重复设置返回相同结果 | PASS |
| — | 持久化失败 500 无半状态：test_持久化失败返回500且不产生半状态（MODEL_PARAMS_PERSISTENCE_FAILED 已登记 APPLICATION_ERROR_STATUS） | PASS |
| AC8 | test_mock模式下参数保存成功且模式不变 | PASS |

## S2 生效链路（待开发）
## S3 前端参数表单（待开发）
