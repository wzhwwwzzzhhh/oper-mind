# P8-model-list-enumeration · 独立审查

> 审查时间：2026-08-12（dev-execute Phase 4）
> 审查方式：readonly 子代理独立审查（写审分离）
> 审查输入：plan.md、PRD、Design、git diff（worktree 工作区）

## 结论：PASS（无 P0/P1）

发现：
- [P3] `docs/接口清单.md` 计数行未随新增接口更新（v1 合计 35→36、前端已接线 33→34、模型设置 7→8）——已修复。
- [P3] plan.md「改动面」未列 `client.ts` / `model-settings.css` / `handlers.ts`（实现必需接线，非越界）——已补列。

## AC 证据表

| AC | 证据 | 结论 |
|---|---|---|
| AC1 | `test_枚举成功返回模型名列表`（API 层）+ `test_枚举成功解析模型名列表`（verify 层，MockTransport 断言仅请求 `/v1/models`） | PASS |
| AC2 | `test_枚举失败返回脱敏状态不暴露响应体` + `test_枚举超时返回timeout` + 401 用例断言响应体原文不泄露 | PASS |
| AC3 | `test_枚举无Key的Provider诚实失败`(NO_API_KEY) + `test_枚举主密钥缺失诚实失败` + 3 个 MODELS_PARSE_FAILED 用例 | PASS |
| AC4 | 响应仅 provider_id/status/models/error_code/meta；`sk-` 仅出现在测试文件 | PASS |
| AC5 | `ModelSettingsPage.test.tsx` 3 个 MSW 用例（成功选下拉填充 model / HTTP_401 脱敏文案 / 新建态禁用+提示） | PASS |
| AC6 | 复用 `VERIFY_TIMEOUT_SECONDS=5.0`；`MAX_MODELS=100`/`MAX_MODEL_NAME_LENGTH=200`/`MAX_RESPONSE_BYTES=1MB` 各有测试 | PASS |
| AC7 | 无共享状态、按请求独立 fetch（设计保证，无测试） | PASS |
| AC8 | 后端 64 passed（含 config/gateway/resolver 回归）；前端 116 passed + typecheck + build | PASS |

## P0/P1 排查要点（均未发现）

- 凭据：生产代码不返回/记录 api_key；测试显式断言 `PLAINTEXT_VALUE not in response.text`、`"invalid api key" not in str(outcome)`。
- 响应体/异常：`_ProviderRequestResult` 只带状态+错误码，响应体不流出；解析失败诚实 `MODELS_PARSE_FAILED`。
- 无副作用：`list_models` 不写 `verify_status`，测试断言枚举后仍 `unknown`/`last_verified_at=None`。
- SSRF：主机校验保留，私有地址测试确认不发请求。
- 新建态降级：按钮禁用+提示已实现并有 MSW 用例。
- 错误码映射：前端 `models_error_message` 覆盖后端全部错误码 + `HTTP_xxx` 通用回退。
- generated.ts 无手改痕迹。
