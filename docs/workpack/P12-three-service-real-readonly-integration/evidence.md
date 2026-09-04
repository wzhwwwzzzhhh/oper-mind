# P12 PostgreSQL、Redis 与 MySQL 真实只读接入 · 实施证据

> 状态：active；S1 → S2 → S3 已实施，离线验证完成；AC14 真实验收待逐目标授权
> 实施 base：`73292fbf4bf1a772849c94f54fe0e0b3e2108c08`

## 前置证据

- Design 已由用户明确确认，独立只读 Review PASS。
- 用户授权最小 `service_registry_kind_valid` 迁移、active Workpack、实施、离线验证和最终实施 PR。
- 本 Workpack 不访问真实 MySQL/PostgreSQL/Redis 或真实模型 Provider。

## S1 证据

- `ServiceRegistry` 从同一 connector entry 派生 typed binding；静态/动态 origin 只保留不可逆摘要。entry 暴露前精确校验 kind、investigation profile 与 capability Protocol。
- 动态 create/update/delete 在同一 service_id guard 内覆盖 DB transaction 与 identity-CAS map mutation；全量投影另持有 mutation-epoch barrier，poisoned entry 对 get/list/service_ids/resolve 一致隔离。
- PostgreSQL Agent-facing capability 是封闭 adapter，只提供 health、explain、index、create-table 与 lock 的类型限定方法，不暴露 connection、engine、DSN 或 generic executor；bound lock Tool 拒绝 database/额外参数。
- 正式 `build_v1_services_for_runtime()` 装配的确定性 E2E 已覆盖：动态注册 → 同 entry 连接测试 → service Session → Run → ToolGateway → 唯一 succeeded 终态 → 安全 Trace/Result；另覆盖 session mismatch 与注册后删除的失败关闭。
- 激活 legacy scenario 后调用 bound PostgreSQL Tool 仍命中 registry capability，证明模型模式不替换服务事实源。

## S2 证据

- Redis definition/API 投影声明唯一 `service_health_pressure.v1`；DBAgent 只注册无参数 `redis_health_overview`。
- 行为 ledger 精确为 `PING`、`INFO memory`、`CLIENT LIST`、`SLOWLOG LEN`；仅投影 memory bytes、client count、slowlog count 与观测状态，原始 client/slowlog/key/value 均不出 capability。
- timeout、permission、malformed fact、主失败+cleanup 失败、主成功+cleanup unknown 均映射为封闭安全状态；源码 mutation gate 对通用/写命令失败。

## S3 证据

- 唯一新增驱动为 `PyMySQL==1.2.0`；DSN 只接受 `mysql+pymysql`、username/host、空 database path 与空 query allowlist。
- Connector 使用 `NullPool` 和固定 connect/read/write timeout，只执行两条固定 GLOBAL SHOW；缺失、重复、负数、超时、权限和 cleanup 故障均安全收敛。
- revision `20260904_15_p12_mysql_kind` 只替换 `service_registry_kind_valid`。SQLite batch、非 SQLite op spy、previous→upgrade 数据保留、安全 downgrade、MySQL row 拒绝回滚、失败后约束仍允许 MySQL、单一 head 与 revision 长度均有确定性测试。
- MySQL CRUD、连接测试、安全 API 投影、ServiceCenter 入口、Workbench intent 与精确 service_id 导航均有后端/前端测试。
- P12 preflight 只验证 opt-in/目标/credential ref；独立 Runner 在 TTY 二次确认后按 kind 选择精确 health Tool，并在成功退出前验证唯一终态、唯一成功 Tool 事件与 Result。Runner 未实际执行。

## AC1–AC18

- **AC1 自动化满足**：正式装配 E2E 证明动态 PG 的连接测试与 Agent Tool 使用同一 registry entry、service_id、capability/origin；Tool 不查动态 env。
- **AC2 自动化满足**：静态 descriptor 与动态记录均经同一 factory/Registry/binding contract；P8 静态 connector 回归通过。
- **AC3 自动化满足**：typed `binding_not_found`、`binding_type_mismatch`、`investigation_not_supported`、`credential_unavailable`、`binding_poisoned`，以及 session mismatch/delete-after-register 探针均在外联前失败，无默认回退。
- **AC4 自动化满足**：正式 PG E2E 形成唯一 succeeded、一个成功 health Tool Trace 和 Result；既有慢查询 Tool 保留受限参数/只读能力。
- **AC5 自动化满足**：Redis Agent 只输出固定结构化标量，无 key/value/原始慢日志。
- **AC6 自动化满足**：四命令 ledger 与通用/写命令源码 mutation negative gate 通过。
- **AC7 自动化满足**：MySQL 复用既有 create/update/delete/test-connection，API 无 DSN 明文并投影 investigation。
- **AC8 自动化满足**：MySQL DSN、短生命周期、超时、未配置/不可达/权限/cleanup/malformed 探针通过。
- **AC9 自动化满足**：MySQL Tool schema 为空对象，只返回固定六项指标与状态；固定 SQL exact gate 通过。
- **AC10 自动化满足**：三类 Tool 统一经 ToolGateway；P11 timeout/late acceptance/唯一结果历史回归通过，P12 timeout map 非法配置拒绝。
- **AC11 自动化满足**：API/Trace/Tool/Runner 负向断言与敏感字面量扫描通过；只保留既有 has_dsn/掩码投影。
- **AC12 自动化满足**：未修改 `tests/conftest.py`，后端全量在 collection-time blocker 下完成，未访问真实服务/模型。
- **AC13 自动化满足**：preflight 复用唯一 validator，覆盖缺项、64 字符、合法/非法 ID、CI/pytest/non-TTY 与“技术前置满足、尚未访问”。
- **AC14 待真实验收**：独立 Runner 与安全验证逻辑已实现/离线测试；本机 MySQL、远端非生产 PostgreSQL、远端非生产 Redis 均未获得逐目标当次访问授权，故未执行；真实模型也未执行。
- **AC15 自动化满足**：聚焦、P10/P11/P12 gate、历史回归、后端全量、Ruff、Mypy、前端 typecheck/test/build、diff check 均通过；无 skip/xfail/xpass 增长。
- **AC16 自动化满足**：exact-path、三服务类型、单 migration、固定 Redis/MySQL 命令、preflight import 与范围扩张 mutation gate 通过。
- **AC17 自动化满足**：Redis/MySQL API investigation 非空；前端分别断言点击卡片后 POST 精确 service_id 并导航固定 intent；未知 intent 保持未启用。
- **AC18 自动化满足**：mock/real 配置不改变 scenario，bound PG 在 active scenario 下仍调用 capability；scripted driver 与 fake service fact 独立。

## 最终验证日志

- P12 聚焦（binding/PG E2E/Redis/MySQL/migration/preflight/Runner/API/gate）：`117 passed`；最终 Review 定向复验另为 `89 passed`。
- P10/P11 Contract Kernel、Runtime Adapter、ToolGateway、regression、P11/P12 gate、service/DB 回归：`190 passed`。
- P12 exact-path 与 mutation negative gate：`11 passed`。
- 后端 Ruff：`All checks passed`；Mypy：`Success: no issues found in 118 source files`。
- 前端聚焦：`10 passed`；前端全量：`22 files / 222 tests passed`；typecheck 与 production build 通过。
- `git diff --check`：通过；P12 gate 的 AST inventory 证明无新增 skip/xfail/xpass。
- 敏感字面量扫描：未发现高置信真实 secret、私钥或 API Key；命中的连接串均为测试用保留地址/占位示例，不是实际目标或凭据。
- 后端全量：`863 passed, 5 warnings`（`399.78s`）；warnings 均为既有依赖弃用告警，无测试失败。

## 未执行的真实验收

- 本机 MySQL：未授权当次访问，未执行。
- 远端非生产 PostgreSQL：未授权当次访问，未执行。
- 远端非生产 Redis：未授权当次访问，未执行。
- 真实模型 Provider：未授权，未执行。
