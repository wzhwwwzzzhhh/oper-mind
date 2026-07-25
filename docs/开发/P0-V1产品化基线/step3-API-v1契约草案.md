# P0 Step3 — API v1 契约草案

> 日期：2026-07-25　|　状态：已完成并提交　|　基线提交：`9c893cd docs: 完成P0.2后端架构盘点`

## Design

P0.2 已确定产品实体、状态机和分层边界。本 Step 将这些设计收敛为 P1/P2 可实现、P3 可消费的单一 API v1 草案：单租户 MVP、UUID、UTC ISO 8601、cursor 分页，且 `RunEvent.sequence` 精确映射到 SSE `id`。

`DiagnosisResult` 是最终结构化事实；旧 `/diagnose` 与 `/diagnose/stream` 仅保留阶段一演示兼容性，不能被包装成持久化 API。契约文本与 Pydantic/TypeScript 类型草案统一放在 `api-v1-contract.md`，本 Step 不创建可导入的源码模型或 FastAPI 路由。

## Step

1. 定义响应元数据、资源元数据、cursor 分页和安全错误体。
2. 定义 Session、Message、DiagnosisRun、RunEvent、DiagnosisResult、Evidence 及嵌套结构类型。
3. 定义创建 Run、SSE 事件帧、`Last-Event-ID` 重放和终态关闭语义。
4. 定义最小端点、状态码、幂等键与失败语义。
5. 声明旧接口边界，更新计划、交接和开发规则；独立审查后等待提交授权。

## Code

- `docs/开发/P0-V1产品化基线/api-v1-contract.md`：Pydantic/TypeScript 草案、端点、SSE、失败与兼容契约。
- `docs/开发/P0-V1产品化基线/step3-API-v1契约草案.md`：本 Step 的设计、范围、验证与审查记录。
- `docs/开发/_A-Plan-总览.md`、`docs/开发/_B-V1产品化开发计划.md`：P0.3 当前入口与完成条件。
- `AGENTS.md`、`CLAUDE.md`、`docs/开发规范.md`：将 API v1 草案作为 P1/P2 的实现边界。

## Test

- 文档与类型草案 Step；不运行 Python/前端测试，不实现可执行模型、ORM、数据库、迁移或 FastAPI 路由。
- 已对照既有 `backend/src/api/schemas.py`、`backend/src/api/events.py`、`backend/src/app.py`，确认旧接口使用无持久化的 Markdown 与 `progress/complete/error` 事件。
- 已对照 P0.2 的 Run 状态机和 `RunEvent.sequence` 设计，确认 SSE 恢复不依赖当前 Coordinator 的最近内存 trace。

## Review

- 已完成独立审查，详见 `docs/开发/P0-V1产品化基线/review.md` 的 P0.3 小节。
- 检查了 Pydantic 与 TypeScript 嵌套字段、UUID/UTC/cursor 默认约束、`RunEvent.sequence` 到 SSE `id` 映射、事件恢复、状态码、幂等、旧接口兼容性和禁止范围。
- 结论：通过；本 Step 只提交文档与类型草案，提交前必须获得用户确认。
