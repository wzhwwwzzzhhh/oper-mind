# M6 Step2 — SSE 流式诊断事件

> 日期：2026-07-24　|　状态：✅ 通过

## Design

在不改变既有 `route()` 同步调用与评测路径的前提下，新增 `CoordinatorAgent.route_stream()`。该方法消费 LangGraph `stream_mode="updates"`，从每个节点返回的累积 trace 中只抽取新增部分，转化为带 UTC 时间戳的 API 事件。

## Step

1. 定义 SSE progress / complete / error 事件模型与序列化函数。
2. 在 Coordinator 中新增 trace 标准化、Agent 启动事件和流式路由。
3. 在 FastAPI 中暴露 `/diagnose/stream`，以 `text/event-stream` 输出。
4. 补充 completion、空请求与图运行异常的测试；回归既有三路 smoke。

## Code

- `src/api/events.py:10-35`
  - `DiagnosisProgressEvent`、`DiagnosisCompleteEvent`、`DiagnosisErrorEvent`。
  - `serialize_sse()` 严格输出 `event:` / `data:` / 空行分隔的 SSE 帧。
- `src/core/coordinator.py:120-179`
  - `_normalize_trace()` 映射旧 graph trace 的节点名为稳定事件 type，并补齐 ISO UTC 时间戳。
  - `_create_start_events()` 在路由完成后即时发送 `agent_start`，便于前端先点亮执行节点。
- `src/core/coordinator.py:216-262`
  - `route_stream()` 以 `graph.stream(..., stream_mode="updates")` 获取节点更新；完成时输出完整 trace；异常只输出通用 `DIAGNOSIS_FAILED`。
- `src/app.py:169-198`
  - `/diagnose/stream` 校验查询参数后返回 `StreamingResponse`；添加禁缓存 / 禁代理缓冲头。
- `tests/test_api.py:100-220`
  - 验证 progress → complete 顺序、SSE Content-Type、空 query 422、标准帧格式、图构建异常、未知内部 trace type 与 SSE 序列化异常。
- `scripts/smoke_pipeline.py:37-39`
  - 冒烟装配关闭长期记忆，确保 smoke 不再写 `data/memory.json`，恢复可复现边界。

## Test

2026-07-24 在隔离 Python 3.12 测试环境执行：

```text
pytest tests/test_api.py -q
11 passed, 1 warning

python scripts/smoke_pipeline.py
✅ 三条路径全部跑通,pipeline 已接通(route → agent → [debate] → report → reflection)

pytest tests -q
83 passed, 1 warning
```

冒烟后确认 `data/memory.json` 保持 25 条记录，未被本次运行污染。

## Review

- 同步 API 与评测继续走 `route()`，流式接口只增加并行入口，未改变 graph 节点与既有 trace node 名称。
- 过程事件来自 LangGraph 的节点完成更新；并行 Agent 的实际完成顺序由原图并发行为决定，`agent_start` 为策略级启动提示，非每个子 Agent 的独立实时回调。
- SSE 断开感知 / 主动取消、审批门的非阻塞交互、鉴权与 CORS 尚未实现，不应把服务直接暴露公网。
- 结论：**通过**。
