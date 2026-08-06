# P6 日志真实源接入 · Design

> 状态：已确认
> 更新：2026-08-06
> 关联：`docs/prd/session/P6-log-source-real.md`（已确认，issue #21）、`docs/design/session/P4.2DBAgent真库Design.md`（真实模式分支）、`docs/design/session/P4.3服务上下文贯通Design.md`（service_id 贯通链路）、`docs/design/knowledge/P6知识检索Design.md`（受管目录只读模式）、`docs/design/service-center/P6Redis服务接入与监控Design.md`（凭据命名空间与诚实降级）、`docs/产品定义.md` §2.1/§4、`docs/开发规范.md` §3/§4/§5、`docs/路线图.md`。

## 1. 目标与范围

一句话目标：让 Log Agent 在**真实模式**下经由受控只读 Connector 分析**绑定服务实例的真实日志源**（日志检索 / 错误聚合 / 慢查询与超时模式），mock 模式行为完全不变。

### 做什么
- 新增日志源 Connector：受管日志目录，按服务实例命名空间的环境变量 `OPERMIND_SERVICE_<INSTANCE_ID>_LOG_DIR` 接入，只读、限时、脱敏、零落库。
- 三个日志工具（`search_logs` / `aggregate_errors` / `query_slow_log`）在真实模式改走 Connector；mock 模式行为不变（S1–S4 评测确定性不受影响）。
- Log Agent 服务上下文贯通：`LogAgent` 接收 `service_id`，日志工具按绑定服务实例解析日志源（复用 P4.3 链路）。
- 未绑定服务 / 未配置 / 失败超时 → 诚实降级文案，不抛异常、不伪造。
- 日志内容经网关 `desensitize` 兜底 + 工具 `audit_summary`，Trace 只展示脱敏摘要，不展示原始日志。

### 明确不做
- 不做日志写入、轮转、删除或任何非只读日志操作。
- 不做外部日志系统（ELK / Loki / CloudWatch 等，后续阶段，需单独 Design）。
- 不做日志接口（HTTP API）形式接入（接口形式需真实外部资源授权，另行 Design）。
- 不做日志源作为服务中心可选项展示（不注册进 `ServiceRegistry`，不新增服务类型）。
- 不改 mock 数据源（`data/scenarios.py`、`data/mock_db.py`）与 S1–S4 评测路径。
- 不新增公开接口、不新增前端页面/前端直连（沿用会话工作台调查入口）。

## 2. 设计决策

### 2.1 日志源形态与配置契约
- **日志源 = 受管日志目录**：环境变量 `OPERMIND_SERVICE_<INSTANCE_ID>_LOG_DIR`，命名空间与 `OPERMIND_SERVICE_<INSTANCE_ID>_DSN` 完全同构（如 `OPERMIND_SERVICE_POSTGRES_PRODUCTION_LOG_DIR`）。仅环境变量、零落库、不打印不记录。
- `config.py` 新增 `load_service_log_dir(instance_id) -> str | None`：未配置返回 None（→ `not_configured`）。instance_id → env 名归一化规则与 `load_service_dsn` 同构（`OPERMIND_SERVICE_{instance_id.upper().replace('-', '_')}_LOG_DIR`，见 `config.py` `load_service_dsn`）。
- 目录内识别文本日志文件；跳过隐藏路径与凭据/配置类文件（`.env`、`*.local.yaml`、`*.key`、`*.pem` 等，复用知识检索排除清单）。
- 关键行为变更（相对 P4.3，需在回归中显式验证）：P4.3 时 Server/Log 调查不依赖服务上下文、真实模式仍返回 mock 日志；本设计在真实模式下按绑定服务解析日志源，未绑定 →「日志源未选择目标服务」，未配置 →「日志源未配置」。这是修复「mock 冒充真实」的预期行为变更，mock 模式不受影响。

### 2.2 日志源 Connector
- 新增 `backend/src/infrastructure/logs/log_source.py`：`LogSourceConnector`。
  - `__init__(log_dir: str | None, instance_id: str)`。
  - 只读能力：`search(keyword, time_range_hours)`、`aggregate_errors()`、`slow_query_patterns(limit, threshold_seconds)`，返回结构化结果（Pydantic / TypedDict，跨层数据禁止隐式字典协议）。
  - 只读约束：仅 `open(..., "r")`；禁止写/删/改名/轮转；有界扫描（单文件读取上限、扫描行数/返回条数上限）；固定 3s 超时（网关已限时，Connector 内再做有界扫描兜底）。
  - 路径安全：检索关键字禁止 `/ \` 与控制字符并限长（对齐知识检索 `_ILLEGAL_QUERY_RE` + `_QUERY_MAX_LEN=100`），不把文件名拼接到任意路径。
  - 越界防护：遍历时对每个候选做 `resolve().relative_to(root)` 解析根前缀校验，符号链接/解析到受管目录外一律拒绝（对齐知识检索 `_collect_docs`，`knowledge_tools.py:138-141`）。
  - 诚实降级：未配置 → `not_configured`；目录不存在 / 不可读 / 超时 → `unavailable`（不暴露异常详情）。
  - 可测性：`log_dir` / Connector 支持构造注入，测试用临时目录或假 Connector，确定性验证真实分支与降级，不依赖真实日志文件。

### 2.3 工具改造（真实分支 + mock 分支）
- 三个日志工具 `__init__` 接收 `service_id`（对齐 db_tools 模式），真实模式（`get_active_scenario()` 为 None）经 `load_service_log_dir(service_id)` → `LogSourceConnector` 读取；mock 模式（场景激活）行为与现有一致。
- 工具内部 `audit_summary()` 返回脱敏摘要（如「日志检索命中 N 条 / 聚合 M 类错误 / 慢查询 K 条」），Trace 只展示摘要不展示原始日志。
- 超时/异常关联：`search_logs(keyword="timeout")` + `aggregate_errors` + `query_slow_log` 组合覆盖，不新增 Tool 契约。

### 2.4 Log Agent 服务上下文贯通
- `LogAgent.__init__` 增加 `service_id`，透传给三个工具；`bootstrap.build_coordinator` 把 `service_id` 传入 `LogAgent`（复用 P4.3 链路）。
- 事件审计（小幅）：`coordinator_executor._event_data` 对 `role == "log"` 同样附 `service_id`，与 db 事件一致。这是诊断事件载荷的增量变更（现仅 role=="db" 附 service_id），需在回归中断言：log 工具事件含 service_id、db 事件行为不变。

### 2.5 诚实降级
| 场景 | 行为 |
|---|---|
| 会话未绑定服务 + 真实模式 | 「日志源未选择目标服务」 |
| 绑定服务未配置日志目录 | 「日志源未配置」 |
| 目录不存在 / 不可读 / 超时 | 「日志源不可用」，不暴露异常详情 |
| mock 模式 | 与现有行为完全一致，S1–S4 确定性不受影响 |

## 3. 文件改动面
- `backend/src/config.py`：`load_service_log_dir(instance_id)`。
- `backend/src/infrastructure/logs/log_source.py`（新增）：`LogSourceConnector` 与结构化结果模型。
- `backend/src/tools/log_tools.py`：`service_id` 注入、真实分支、`audit_summary`、mock 分支保留。
- `backend/src/agents/log_agent.py`：接收并透传 `service_id`。
- `backend/src/core/bootstrap.py`：`LogAgent` 传入 `service_id`。
- `backend/src/infrastructure/diagnosis/coordinator_executor.py`：log 工具事件附 `service_id`。
- 测试：`backend/tests/test_log_source.py`（新增）、`backend/tests/test_log_tools_real.py`（新增）；回归 `test_agent_gateway.py`、`test_diagnosis.py`、`test_tool_gateway.py`、`test_api.py`、`test_knowledge_agent.py`（路由）。
- 明确无：无公开 API 变更、无数据库迁移、无前端功能改动。

## 4. 切片与验证（指引，不写死）
- 建议拆 2 片，每片独立可验收：
  - S1：日志源 Connector + 配置 + 有界只读扫描 + 诚实降级与脱敏（含单元测试）。
  - S2：三工具真实分支 + LogAgent 服务上下文贯通 + 事件审计 + mock 回归与端到端验收（AC1–AC7）。
- 门禁项：新 Connector（日志源）、真实连接（受管目录）、凭据（环境变量）→ 本 Design 即满足 Design → Review → 用户确认。
- 验证命令由 dev-plan 的 plan.md 落定（pytest / git diff --check）。

## 5. 风险、回滚与门禁
- 风险集中在凭据泄漏、越权文件访问与超时拖慢：由「环境变量零落库 + 只读白名单 + 路径逃逸拦截 + 凭据文件排除 + 有界扫描/限时 + 网关脱敏兜底」防护。
- 回滚：移除 Connector/工具真实分支即回退，无迁移、无公开 API、不触碰 mock 路径；LogAgent `service_id` 贯通回退不影响 DB 链路。
- 门禁：新 Connector + 真实连接需 arch-review PASS + 用户确认后放行 dev-plan。

## 6. 待用户确认的设计决策
1. **日志源形态**：受管日志目录（`OPERMIND_SERVICE_<INSTANCE_ID>_LOG_DIR`，建议）vs 日志接口（HTTP API，需外部资源授权，排除）。是否确认受管目录？
2. **检索粒度**：行级文本检索 + 从日志行按模式解析慢查询/超时（建议）；不做文件级/二进制解析。是否确认？
3. **Tool 契约**：不新增工具，沿用三个既有日志工具真实分支（建议）；mock 行为不变。是否确认？
4. **服务上下文**：LogAgent 增加 `service_id` 贯通，日志源按绑定服务实例解析（建议）；未绑定 →「未选择目标服务」。是否确认？
