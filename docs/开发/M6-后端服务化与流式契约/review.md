# M6 Review — 后端服务化与流式契约

> 审查日期：2026-07-24　|　分支：`feat/m6-backend-sse`
> 状态：✅ 通过

## 验收结果

| 验收项 | 结果 | 证据 |
|---|---|---|
| 稳定 HTTP 契约 + 统一错误体 | ✅ | `src/api/schemas.py`；`tests/test_api.py` 同步与校验覆盖 |
| SSE 逐节点事件 | ✅ | `/diagnose/stream` 输出 `progress`，并以 `complete/error` 终止 |
| mock 与三条 pipeline 回归 | ✅ | 2026-07-24：smoke direct / chain / parallel 通过 |
| 全量单测 | ✅ | 2026-07-24：`83 passed, 1 warning` |
| API Key 不泄露 | ✅ | `/health` 只返回 `status/mode/model` |

## 最终 SSE 契约

- SSE event name：`progress` / `complete` / `error`。
- `progress.data`：`type`、`node`、`detail`、`timestamp`。
- progress type：`route_decided`、`agent_start`、`agent_done`、`conflict_checked`、`debate_round`、`report`、`reflection`。
- `complete.data`：`result`、`strategy`、完整 `trace`。
- `error.data`：`code`、`message`；不含内部异常细节。

## 审查发现与处置

1. **FastAPI 不能将 `StreamingResponse | JSONResponse` 作为自动响应模型**：已通过 stream 路由的 `response_model=None` 和基类 `Response` 返回类型处理，避免启动时报 Pydantic schema 错误。
2. **旧 smoke 会写长期记忆文件，导致回归污染**：已在 smoke 装配中明确关闭长期记忆。
3. **API 服务未接入鉴权**：保留为 demo 限制，已在 `design.md` 和 Step2 中明确写出，M8 联调前不得公网部署。
4. **独立代码审查发现 SSE 异常边界缺口**：`_ensure_graph()` 原在 `route_stream()` 的 `try` 之外，且未知内部 trace type 可能使 Pydantic 序列化中断流。已将图构建纳入安全错误分支、以 node 映射作为公开事件类型单一来源，并在 SSE 适配层兜底 `KeyError` / `TypeError` / `ValidationError`；新增对应回归测试。

## 已知限制 / 后续建议

- SSE 尚不感知浏览器断开，长任务不会因客户端离开而取消。
- Agent 节点目前按策略级提示 `agent_start`；若 M7 需要每个并行 Agent 独立即时点亮，需要在 graph 内加入回调/事件队列。
- 当前 `approval.py` 的阻塞 `input()` 尚未转换为可交互的 API 审批流；本阶段不触发该功能。
- 不包含 CORS、鉴权、限流；这些进入 M8 端到端打磨。

## 关联提交

- `2c41421 feat: 完成M6流式诊断接口`
