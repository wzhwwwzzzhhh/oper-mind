# P6-log-source-real · 工作包计划

## 范围

### 只做

- AC1：`search_logs` 等日志工具在真实模式（场景未激活）返回绑定服务实例真实日志源的只读检索结果，而非场景 mock 数据。
- AC2：日志源未配置（无 `OPERMIND_SERVICE_<INSTANCE_ID>_LOG_DIR`）→ 「日志源未配置」降级文案，不崩溃、不伪造。
- AC3：日志源目录不存在 / 不可读 / 超时（模拟）→ 「日志源不可用」，不暴露异常详情。
- AC4：mock 模式（`set_active_scenario("S1")`）下日志工具返回原 mock 结果，与改动前一致（S1–S4 确定性不变）。
- AC5：日志分析结果不出现凭据、DSN、`sk-`、原始异常全文；日志行脱敏后进入上下文。
- AC6：日志工具输出经网关限时（3s）与 `desensitize` 脱敏兜底；Trace 只展示工具名/状态/耗时/`audit_summary` 脱敏摘要，不展示原始日志全文。
- AC7：回归 —— `test_agent_gateway.py`、`test_diagnosis.py`、`test_tool_gateway.py` 全绿。
- 新增 `load_service_log_dir(instance_id)`：命名空间 `OPERMIND_SERVICE_{instance_id.upper().replace('-', '_')}_LOG_DIR`，仅环境变量、零落库。
- `LogSourceConnector`：受管目录只读扫描（行级文本检索 / 错误聚合 / 慢查询与超时模式解析），有界读取 + 路径逃逸/符号链接越界拦截 + 凭据文件排除。
- Log Agent 服务上下文贯通：`LogAgent` 接收 `service_id` 并透传日志工具；`coordinator_executor` 对 `role=="log"` 事件附 `service_id`（db 事件行为不变）。

### 明确不做

- 日志写入、轮转、删除或任何非只读日志操作。
- 外部日志系统（ELK / Loki / CloudWatch 等）与日志接口（HTTP API）接入。
- 日志源注册进 `ServiceRegistry` 或服务中心展示（不新增服务类型）。
- 新增公开接口、新增前端页面/前端直连、数据库迁移。
- 修改 mock 数据源（`data/scenarios.py`、`data/mock_db.py`）与 S1–S4 评测路径。
- 修改工作包外的文件。

## 切片拆分（2 个独立可验收切片）

- [ ] S1：日志源 Connector 与配置（`config.py` + `infrastructure/logs/log_source.py` + `test_log_source.py`），覆盖 AC1 的数据通路、AC2/AC3 降级、AC5 脱敏前提、AC6 有界/越界防护。
- [ ] S2：三工具真实分支 + LogAgent `service_id` 贯通 + 事件审计 + mock 回归（`log_tools.py` + `log_agent.py` + `bootstrap.py` + `coordinator_executor.py` + `test_log_tools_real.py` + 回归套件），覆盖 AC1–AC7 端到端。

## 改动面

### 后端

- `backend/src/config.py`：新增 `load_service_log_dir(instance_id)`。
- `backend/src/infrastructure/logs/log_source.py`（新增）：`LogSourceConnector` 与结构化结果模型（Pydantic / TypedDict）。
- `backend/src/tools/log_tools.py`：三工具接收 `service_id`，真实模式走 Connector，mock 分支保留 `active_or_default()` 原行为，新增 `audit_summary()`。
- `backend/src/agents/log_agent.py`：接收并透传 `service_id` 到三工具。
- `backend/src/core/bootstrap.py`：`build_coordinator` 把 `service_id` 传入 `LogAgent`。
- `backend/src/infrastructure/diagnosis/coordinator_executor.py`：`_event_data` 对 `role=="log"` 附 `service_id`（db 事件行为不变）。
- `backend/tests/test_log_source.py`（新增）、`backend/tests/test_log_tools_real.py`（新增）。
- 回归：`test_agent_gateway.py`、`test_diagnosis.py`、`test_tool_gateway.py`、`test_api.py`、`test_knowledge_agent.py`。

### 前端

- 无功能改动（沿用会话工作台调查入口，不新增页面）。

### 明确无

- 无公开 API 变更、无数据库迁移、无凭据落库。

## 验证方法

- 后端聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_log_source.py -q`、`tests/test_log_tools_real.py -q`。
- 后端回归：`..\.venv\Scripts\python.exe -m pytest tests/test_agent_gateway.py tests/test_diagnosis.py tests/test_tool_gateway.py -q`；再跑 `tests/test_api.py tests/test_knowledge_agent.py -q`。
- 门禁：`git diff --check` 干净；检查暂存范围仅本工作包文件；敏感字面量扫描（无 `sk-`、凭据、DSN、`OPERMIND_*` 实际值）；确认 mock 路径与 S1–S4 回归通过。
- 测试用临时目录/假 Connector 注入，确定性验证真实分支与降级，不依赖真实日志文件。

## 提交计划

- S1：`feat: 增加日志真实源只读 Connector 与配置`
- S2：`feat: 日志工具真实分支与 LogAgent 服务上下文贯通`

## 前置设计

- 设计文档：`docs/design/session/P6日志真实源接入Design.md`
- 设计状态：已完成 Design → Review（arch-review PASS，无 P0/P1）→ 用户确认（2026-08-06 确认四项设计决策）。
- 门禁项：新 Connector（日志源）、真实连接（受管目录）、凭据（环境变量）—— 已由已确认 Design 满足。

## 分支与工作区

- 分支：`feat/P6-log-source-real`（基线 `main`，commit `0f532ab`）
- worktree：`D:/market-handsome/oper-mind-worktrees/P6-log-source-real`（开发在 worktree 内进行，主仓库工作区不直接开发）
