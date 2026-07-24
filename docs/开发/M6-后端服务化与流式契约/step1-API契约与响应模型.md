# M6 Step1 — API 契约与响应模型

> 日期：2026-07-24　|　状态：✅ 通过

## Design

将原先集中在 `src/app.py` 的临时 `BaseModel` 拆出为 API 层契约，并统一 FastAPI 的参数校验、业务异常与未知异常响应格式。目标是让 M7 不必从 Python 实现细节猜字段。

## Step

1. 新建 `src/api/`，作为 HTTP/SSE 数据契约边界。
2. 定义同步诊断、trace、错误、健康检查等 Pydantic 模型。
3. 将 `POST /diagnose` 改为使用契约模型；保留旧的 memory 路由，但未实现的清理接口返回 501，而不再伪造成功。
4. 新增 API 回归测试，覆盖健康检查、同步诊断和参数校验。

## Code

- `src/api/schemas.py:8-111`
  - `TraceEventType` 固定前端可识别的事件类型。
  - `DiagnoseRequest` / `StreamQuery` 统一裁剪空白并拒绝空 query。
  - `ErrorResponse` 与 `ErrorDetail` 固定错误结构，拒绝未约定字段。
- `src/app.py:40-81`
  - 三类异常统一输出：请求校验为 `VALIDATION_ERROR`，业务 HTTP 异常为 `HTTP_ERROR`，未知异常为 `INTERNAL_ERROR`。
- `src/app.py:153-167`
  - 同步 `/diagnose` 在 `show_thinking=true` 时返回 Pydantic 校验后的 trace；默认控制响应体大小。
- `src/app.py:143-150`
  - `/health` 返回 `status/mode/model`，不返回 API Key。

## Test

2026-07-24 在新建的隔离 Python 3.12 测试环境中执行：

```text
pytest tests/test_api.py -q
11 passed, 1 warning
```

其中 Step1 覆盖：健康检查无密钥泄露、同步诊断的 trace 契约、空 query 的统一 422 错误体。

## Review

- 已检查响应模型均为 Pydantic 数据结构，公开函数带类型标注。
- 未把异常原文、配置或 API Key 回传到客户端。
- 结论：**通过**。已知限制见 M6 总 review：鉴权、真实网络端到端与 CORS 留待 M8 联调阶段处理。
