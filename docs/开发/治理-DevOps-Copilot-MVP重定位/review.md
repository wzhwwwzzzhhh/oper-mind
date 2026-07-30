# P4.0 Review — DevOps Copilot MVP 重定位与 Work 1 边界

> 更新：2026-07-30　|　结论：**通过。Work 1 靶场已真实验收；P4.1 仍未授权。**

## 定位复核

- [x] 当前主线是“调查—提案—审批—白名单执行—验证”的 DevOps Copilot 产品闭环，不是多 Agent 实验平台。
- [x] `frontend/` 是未来产品主界面，`report/` 继续为研发/Trace/评测控制台。
- [x] P3.5/P3.6 长会话路线已封存为可复用技术成果，不再占用产品主线。

## Work 1 安全与真实性复核

- [x] 用户确认可在其本地隧道 `127.0.0.1:5433` 创建并使用新数据库 `opermind_demo`。
- [x] 控制脚本硬限制数据库、schema、表、索引与本地服务地址；配置不匹配立即失败。
- [x] 没有访问、探测、读取、写入或清理 `gongkar` 的代码路径；凭证仅从进程环境读取。
- [x] 故障仅删除预定义索引，恢复仅重建该索引；无用户输入 SQL、无 LLM SQL、无任意 Shell。
- [x] 真实验收同时依赖执行计划、延迟窗口和 JSONL 日志，不会将命令退出成功伪装为业务恢复。
- [x] `clean` 只删除 `opermind_demo` schema 和 `runtime/`，不删除数据库或其他资源。

## 真实 smoke 复核

2026-07-30 运行 `backend/scripts/smoke_demo_orders.py --samples 10` 成功：

- baseline：`Index Scan`，P95 `60.539 ms`，无慢查询日志；
- degraded：`Seq Scan`，P95 `84.127 ms`，P50 增加 `24.749 ms`、`1.460x`，10 条匹配慢查询日志；
- recovered：恢复 `Index Scan`，P95 `61.451 ms`，慢查询日志归零；
- smoke 默认 clean 后确认专用 schema 不存在。

## 未解决项

- Work 1 尚未把靶场接入 OperMind 的 DB/Log/Server Agent；
- 尚未有产品化的审批、执行、Verify application service、API/SSE 和前端；
- 应用元数据与诊断数据源隔离、最小权限账号与 mock fallback 必须在 P4.1/P4.2 独立设计。

**Review 决定：**可以提交 Work 1；不能据此开始 P4.1。下一步需用户发起并授权新的 P4.1 Design。