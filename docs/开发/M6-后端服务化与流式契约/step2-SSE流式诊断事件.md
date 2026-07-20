# M6 Step2 — SSE 流式诊断事件

> 状态：⚪ 计划（待开工时填写）

## 计划改动文件

- 新增 `src/api/events.py` —— 定义 SSE 事件类型（route_decided / agent_start / agent_done / debate_round / reflection / report）与序列化。
- `src/app.py` —— 新增 SSE 端点（如 `GET /diagnose/stream`），把编排 trace 逐条推送。
- `src/core/coordinator.py` / `src/core/graph.py` —— 在编排关键节点发出事件（回调或生成器），不破坏现有同步调用路径。

## 待填

- [ ] 事件契约定稿（与 M7 前端对齐）
- [ ] 阻塞审批 input() 在流式下的替代方案（当前 approval 用阻塞 input，SSE 下会挂）
- [ ] Code 锚点 + Test（含断线/中途异常）
