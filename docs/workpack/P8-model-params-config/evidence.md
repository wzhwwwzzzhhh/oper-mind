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

## S2 生效链路（已完成）

验证记录：
- `pytest tests/test_llm_client.py -q` → 8 passed（未配置默认 0.0 / 构造注入 0.5 真进调用链 / 显式传参覆盖 / max_tokens 不传与传入 / mock 路径不读参数 / tools 路径并存）
- `pytest tests/test_diagnosis.py tests/test_agent_gateway.py tests/test_api.py tests/test_p2_api_v1.py -q` → 回归通过
- 全量后端回归（见 S2 提交时后台记录）
- `git diff --check` 干净

| AC | 证据 | 状态 |
|---|---|---|
| AC1 | test_构造默认temperature进入调用链：default_temperature=0.5 → SDK kwargs temperature=0.5 | PASS |
| AC2 | test_未配置参数时使用默认temperature（0.0）+ test_未配置max_tokens不传SDK | PASS |
| AC8 | test_mock路径不读参数：default 0.9/99 下 mock 仍返回确定性回复 | PASS |
| — | test_显式传参覆盖实例默认：既有 graph/debate 显式 0.0 调用点行为不变 | PASS |
| — | test_构造默认max_tokens进入调用链 / test_显式max_tokens覆盖实例默认 | PASS |
| — | test_tools调用仍带工具参数且temperature生效 | PASS |

## S3 前端参数表单（已完成）

验证记录：
- `npm run typecheck` → 通过
- `npm run test` → 17 files / 130 passed（含 3 个新参数测试：未配置默认标注 / 保存后展示已配置值 / mock 模式标注仅 real 生效）
- `npm run build` → 通过
- `npm run generate:api`（OpenAPI 落盘方式）→ generated.ts 含 ModelParams 类型
- `git diff --check` 干净

| AC | 证据 | 状态 |
|---|---|---|
| AC5 | 未配置参数时展示默认值标注（默认 0/不限制）+ 保存后展示已配置值（0.5 / 4096） | PASS |
| AC7 | 表单仅 temperature / max_tokens 两字段，无 top_p 等未进 chat() 的参数 | PASS |
| AC8 | mock 模式标注「参数不生效，切换 real 后立即生效」 | PASS |
| AC9 | typecheck / test（130）/ build 全绿；后端回归见各切片记录 | PASS |

## 汇总（S1–S3 全部完成）

验证记录：
- 后端全量 `pytest tests -q` → 全绿（S2 提交时后台记录）
- 前端 typecheck / test / build → 全绿
- `git diff --check` 干净
