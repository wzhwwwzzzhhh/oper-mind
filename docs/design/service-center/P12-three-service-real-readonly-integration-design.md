# P12 PostgreSQL、Redis 与 MySQL 真实只读接入 · 实施 Design

> 状态：用户已确认，进入实施；active Workpack 已授权创建
> 更新：2026-09-04
> Issue：[#124](https://github.com/wzhwwwzzzhhh/oper-mind/issues/124)
> PRD：[P12-three-service-real-readonly-integration.md](../../prd/service-center/P12-three-service-real-readonly-integration.md)
> 基线：`origin/main@73292fbf4bf1a772849c94f54fe0e0b3e2108c08`
> 上游：[P8 服务注册](../../prd/service-center/P8-service-registration.md)、[P11 Harness 安全门](../../prd/agent-runtime/P11-harness-real-runtime-safety-gate.md)

## 1. 决策结论与阶段边界

P12 在一个 Workpack 内按顺序实施三个紧密切片：

1. **S1：统一服务 Binding 与 PostgreSQL 端到端接线**。`ServiceRegistry` 持有唯一、不可变、typed 的运行时 binding；动态密文与静态环境变量只在受信装配边界解析，之后共享同一 capability 语义。DBAgent 不再按 `service_id` 查询环境变量。
2. **S2：Redis 最小 Agent 只读调查**。只开放无模型参数的 `redis_health_overview`，其 capability 只可执行固定 `PING`、`INFO memory`、`CLIENT LIST`、`SLOWLOG LEN`。
3. **S3：MySQL 最小真实只读接入**。增加一个最小 CHECK 约束迁移、固定版本 PyMySQL 驱动、MySQL Connector/capability、服务中心入口和无参数健康调查；不开放任意 SQL、管理命令或业务数据读取。

P12 新增的唯一统一调查 intent 定为 `service_health_pressure.v1`，中文展示名为“服务健康与连接压力概览”。三类服务共享该 intent 与 ToolGateway，但由 binding 的服务类型选择封闭 capability；PostgreSQL 继续保留既有受控调查能力，同时把该 intent 映射到既有只读工具组合。

本 Design 明确允许一条经用户单独授权的最小迁移：只把 `service_registry_kind_valid` 从 `postgres/redis` 扩展为 `postgres/redis/mysql`。不新增表、字段、索引、数据回填或凭据语义。

P12 不接入 Prometheus、Loki 或其他服务，不新增公开端点/字段，不引入 Task/Attempt/Recovery/全局 Run deadline/跨进程取消，不改变高风险动作边界，不访问真实资源。真实验收软件可以实施，但实际运行始终留在用户逐目标当次授权之后。

## 2. 前置门与当前代码事实

### 2.1 需求、Git 与工作区门

- 已执行 `git fetch origin main`；Git ref 与 GitHub 远端均核对 `origin/main` 为 `73292fbf4bf1a772849c94f54fe0e0b3e2108c08`。
- 该提交包含 P12 PRD，frontmatter 为 `status: 已确认`、`phase: P12`、`issue: 124`；Issue #124 为 OPEN。
- Design 分支为 `codex/p12-124-implementation-design`，独立 worktree 从上述 SHA 创建且工作区初始干净。
- P12 只有一个 PRD、一个 Issue；当前没有 P12 active Workpack。本阶段不得创建。

### 2.2 当前服务注册与运行链

当前正式链路为：

```text
env 静态 DSN ─→ dependencies.py 直接构造 Connector ─┐
                                                      ├→ ServiceRegistry → 服务中心/监控/Session 校验
动态密文 ─→ bootstrap 解密 ─→ Connector Factory ─────┘

Run.service_id → coordinator_factory → DBAgent(service_id)
              → db_tools.load_service_dsn(service_id) → 环境变量 DSN
```

因此动态注册连接测试和 Agent Tool 存在两个事实源：Connector 使用解密后的动态 DSN，DBAgent Tool 仍只查环境变量。模型 Provider 构建还会通过进程级 scenario 开关切换 Tool 事实来源，使“模型模式”和“服务事实源”耦合。

现有安全与兼容资产：

- `ServiceRegistry` 已是服务中心、监控、Session/Run service_id 校验的共享对象；公开服务视图只投影 `has_dsn` 与有限掩码尾号。
- PostgreSQL/Redis Connector 已有连接/操作超时、结构化快照和安全异常收敛；P11 已用 deterministic fake 证明资源级超时、只读、命令集合、cleanup 和 ToolGateway 迟到隔离。
- `RunApplicationService` 是唯一 Run/Result/Message/RunEvent 业务写入者；P11 runtime guard 保证正常 EOF 只有一个终止结果，异常映射到既有 `DIAGNOSIS_FAILED`。
- `tests/conftest.py` 在 pytest collection 前清除真实 DSN 并阻断 DNS、socket、SQLAlchemy 非 SQLite、Redis、HTTP 和模型外联；P12 不修改或削弱它。
- 前端服务中心已经按 `supported_investigations` 决定“发起调查”是否可用，但创建表单只接受 PostgreSQL/Redis，Workbench 只认识既有 PostgreSQL intent。

### 2.3 已确认的最小迁移必要性

`service_registry.kind` 是普通字符串字段，但 ORM model 与 P8 Alembic migration 都有：

```sql
CHECK (kind IN ('postgres', 'redis'))
```

AC7 要求 MySQL 通过现有 API 动态注册；仅扩展 Pydantic 白名单会在数据库层失败。用户已明确授权 P12 Design 纳入一条仅替换该 CHECK 的迁移，约束见 §7.4。

## 3. 唯一 typed service binding / capability 边界

### 3.1 类型与职责

在 `src.domain.services` 定义 capability Protocol、Registry 内部 binding 与 Agent 窄视图，避免 domain 反向依赖 application。基础设施实现 capability；Agent 只得到调查所需最小能力：

```python
ServiceKind = Literal["postgres", "redis", "mysql"]
InvestigationId = Literal["service_health_pressure.v1", ...既有 PG 调查]

@dataclass(frozen=True)
class BindingOrigin:
    kind: Literal["registry", "env"]
    source_fingerprint: str  # 只在 Registry/Runner 侧可见的单向摘要

@dataclass(frozen=True)
class RegistryBinding:
    service_id: str
    kind: ServiceKind
    definition: ServiceDefinitionData
    connector: ServiceConnector
    capability: PostgresReadonlyCapability | RedisHealthCapability | MysqlHealthCapability
    origin: BindingOrigin

@dataclass(frozen=True)
class BoundServiceCapabilities:
    service_id: str
    kind: ServiceKind
    supported_investigations: tuple[InvestigationId, ...]
    capability: PostgresReadonlyCapability | RedisHealthCapability | MysqlHealthCapability
```

`RegistryBinding` 是 Registry/Application 内部对象；它的 connector、origin 都不得传给 Coordinator/Agent。`BoundServiceCapabilities` 是唯一 Agent-facing view，不含 connector、provenance、DSN、环境变量名、密文或 nonce。capability 实例可以在受信进程内私有持有连接配置，但只暴露类型限定的方法，不提供 `execute(sql)`、`execute(command)`、网络客户端或凭据 getter。

为兼容现有服务中心/监控，`ServiceRegistry` 仍以现有 connector entry 为底层唯一映射；每个生产 connector 同时私有组合一个同源 capability 和 origin。Registry 在解析时从同一个 entry 创建不可变 `RegistryBinding`，不维护第二个 target/capability map。现有仅投影 connector 的测试 fake 可继续注册，但没有 capability 的 entry 无法解析为调查能力。

Registry 提供两个分层解析口：

```python
resolve_registry_binding(
    service_id: str,
    *,
    expected_kind: ServiceKind | None,
) -> RegistryBinding

bind_for_agent(
    binding: RegistryBinding,
) -> BoundServiceCapabilities
```

生产 entry 在 bootstrap、`add_if_absent()`、`replace_if_same()` 暴露前执行 `validate_entry_contract()`：definition.kind、`supported_investigations`、capability Protocol、封闭 kind profile 和 Tool 名集合必须精确一致；不一致的 entry 不能进入 map，因此也不能出现在 list/API。`bind_for_agent()` 保留同一校验作为二次防御，不是第一次发现半接入的地方。

解析失败使用封闭 typed failure：`not_found`、`type_mismatch`、`investigation_not_supported`、`credential_unavailable`、`binding_poisoned`。在返回 binding 之前不创建连接、不访问网络。`get_connector()`/`list_connectors()` 继续作为服务中心与监控的兼容只读投影，与 binding 来自同一个 entry。malformed production entry 的 bootstrap/register/replace 均用 deterministic fake 证明在公开前失败。

### 3.2 唯一生产接线点

```text
动态注册密文 ─┐
               ├→ build_service_connector() → ServiceRegistry（唯一目标/能力事实）
静态 env DSN ──┘                                    │
                                                  ├→ ServiceCenter/Monitor connector 投影
Session/Run 显式 service_id ─→ resolve_registry_binding ┤
                                                  └→ BoundServiceCapabilities → Coordinator → DBAgent → typed capability
                                                                    │
                                                                    └→ ToolGateway → 固定只读调用
```

具体接线点：

- `backend/src/api/v1/dependencies.py::build_v1_services_for_runtime()` 是唯一装配入口。静态 DSN 仅在这里读取；动态 DSN 仅在这里或注册 Application Service 的受信 factory 边界解密。
- 既有 `backend/src/infrastructure/services/service_connector_factory.py::build_service_connector()` 扩展为三类服务唯一 factory；它一次创建 connector、私有同源 capability 与 origin，不新增平行 factory。
- `_resolved_coordinator_factory()` 接收共享 registry，在每个 Run 构建 Coordinator 前以 `Run.service_id` 解析 Registry binding；`bind_for_agent()` 二次验证 definition 与 capability/Tool profile 一致后，只把 `BoundServiceCapabilities` 窄视图传给 `build_coordinator()`。
- `DBAgent` 构造参数从 `service_id` 改为 `BoundServiceCapabilities | None`；根据 kind 和 capability profile 注册对应 Tool。Tool 构造器接收窄 capability，不接收 connector/service_id/DSN/provenance。
- DBAgent 的 system prompt 与 tool-calling example 由封闭 kind profile 生成：PostgreSQL 保留既有慢查询说明并加入无参数 health Tool；Redis/MySQL prompt 只描述各自无参数 health Tool，禁止 SQL/命令/目标参数。prompt profile 与 ToolRegistry 的工具名集合必须精确一致，否则构造失败，防止 UI 声明已启用但模型仍只理解 PostgreSQL。
- `RunApplicationService` 仍是唯一业务事实 writer；binding/registry 不写 Run、Result、Trace 或 Message，不形成第二套 Run 事实源。

Session 创建和 Run 接纳继续先校验 registry membership。数据库调查还必须显式属于 Session；多服务 Session 没有 service_id 时继续在外联前拒绝。随后 coordinator factory 再做 kind/investigation 校验，防止接纳与执行之间被删除或替换。

### 3.3 静态与动态统一语义

- 静态 env 是 bootstrap 输入，不是 Tool 的运行时查询源；删除 `db_tools._real_connection()` 对 `load_service_dsn()` 的依赖。
- 动态记录是持久化输入；密文在受信装配边界解密后构造同一种 binding。
- 静态 bootstrap 使用显式 `StaticServiceDescriptor(service_id, credential_env_name)` 列表；不从任意 service_id 再派生环境变量名，避免点号/下划线/连字符规则形成第二份映射。同一个 `service_id` 同时出现在静态和动态来源时启动失败关闭，禁止优先级、覆盖或默认回退。
- origin 在受信侧计算 `sha256("registry:<service_id>")` 或 `sha256("env:<descriptor 中的精确 env name>")`；只保存单向摘要。Runner 对 credential_ref 做同样的固定前缀解析和摘要比较，不读取 DSN、不反推 env 名，也不把 origin 交给 Agent。
- `ServiceRegistry` 为每个 service_id 提供 `mutation_guard(service_id)`；guard 覆盖数据库 transaction、commit/rollback 与 map mutation 的全过程。同一 ID 的 resolve/get/list 投影在读取该 entry 前获取同一 guard，其他 ID 不受阻塞。动态注册的全量 list 另获取只用于 mutation epoch 的读 barrier，避免看见 DB 已提交但 map 尚未交换的瞬间；它只短暂阻塞列表，不阻塞其他 ID 的 Run。锁表/barrier 只保存同步对象，不保存目标/凭据，不是第二事实源。
- map mutation 使用 identity-CAS：`add_if_absent(candidate)`、`replace_if_same(old, candidate)`、`remove_if_same(old)`；另有 `poison_if_same(service_id, expected, safe_definition)`，只在同一 map 把该 ID 替换为无 connector/capability/credential 的 typed tombstone。该 ID 随后统一返回 `binding_poisoned`，其他服务继续可用；进程重启从数据库重建并清除瞬时 poison。
- create 在 `mutation_guard(id)` 内执行：校验/加密/构造候选（不外联）→ DB insert+flush+commit → registry add。commit 失败 rollback 且 map 不变；理论上不会失败的 add 若出现 invariant 异常，则把该 ID poison 并返回 `SERVICE_BINDING_CONSISTENCY_FAILED`。
- update：在 guard 内读取 DB row 与旧 entry → 构造/验证候选 → DB update+flush+commit → `replace_if_same(old,candidate)`。commit 失败 rollback 且继续暴露 old；commit 后 CAS 异常只 poison 同一 ID，重启后从已提交 DB row 恢复。
- delete：在 guard 内读取 DB row 与旧 entry → DB delete+flush+commit → `remove_if_same(old)`。commit 失败 rollback 且 old 不变；commit 后 CAS 异常只 poison 同一 ID。不存在的动态行仍幂等，静态 entry 不删除。
- 因候选只在 DB commit 成功后写 map，且同 ID reader 在 guard 释放前阻塞，不会观察未提交 candidate。故障注入覆盖并发 reader+commit failure、每个 mutation 失败点、poison 后同 ID fail-closed、其他 ID 正常可读；不做跨进程原子性声明。
- update 创建新 binding 后原子替换；已开始 Run 持有旧不可变 binding，允许本次调用自然结束，不声称凭据被实时撤销。新 Run 只解析新 binding。这是进程内一致性边界，不虚构 credential lease 或跨进程撤销。

## 4. 模型 Provider 与服务事实来源正交

定义两个互不推导的装配维度：

| 维度 | 合法值 | 决定什么 | 不得决定什么 |
|---|---|---|---|
| Model driver | deterministic mock、deterministic scripted、real provider | Agent 如何选择/编排已注册 Tool | service_id、DSN、binding、是否外联服务 |
| Service fact source | deterministic fake binding、registry binding | Tool 从 fake 还是绑定服务读取事实 | 模型 Provider、Prompt 或模型凭据 |

实施要求：

- `build_llm_from_config()` 不再调用 `set_active_scenario()`/`clear_active_scenario()` 改变 Tool 事实源；模型配置只构造 LLM。
- 生产 v1 始终显式使用 `registry binding`；测试/evaluation 只有在 factory 参数显式传入 `deterministic fake binding` 时才使用 fake。
- 既有 scenario 数据可以作为历史评测夹具保留，但不得在 service-bound Tool 内优先于 binding，也不得由 `api_key == mock` 隐式启用。
- deterministic fake capability 验证事实、异常、超时和脱敏；deterministic local scripted model 只产出固定 Tool 选择，既不模拟服务事实，也不访问模型 Provider。
- 真实模型 Provider 是可选的另一重验收；其授权、凭据和证据不得与真实服务授权合并。

正交探针覆盖 2×2 组合：mock/real 模型配置切换不改变同一 binding identity；fake/registry binding 切换不改变模型实例或 Tool schema。real provider 组合只做装配 fake，不实际外联。

## 5. S1：PostgreSQL 同源端到端

### 5.1 capability 与 Tool

`PostgresReadonlyCapability` 封装现有 PostgreSQL Tool 所需的受控方法；每个方法延续现有 SQL 类型校验、标识符限制、`SET TRANSACTION READ ONLY`、statement timeout、rollback 和 owned-engine dispose。它不暴露通用 connection 或 SQL executor。

现有 `ExplainTool`、`ShowIndexTool`、`ShowCreateTableTool`、`CheckLockStatusTool`、`CheckConnectionPoolTool` 改为注入 capability。模型可见参数保持既有受限 schema，但移除/禁止 service_id、DSN、数据库名、host 和 credential 参数。Tool 捕获 Run 已绑定 capability，因此不能跨目标。

`service_health_pressure.v1` 对 PostgreSQL **只调用一次**既有 `check_connection_pool` 的 typed capability，Tool schema 固定为空对象，scripted driver 调用顺序固定为“调用该 Tool → 根据返回事实结束”。底层顺序固定为 connect → `SET TRANSACTION READ ONLY` → 连接状态 SELECT → max_connections SELECT → cleanup；按每步 3s、cleanup 1s 计算 whole-call 上界 13s，Gateway wait 为 15s。返回 `PostgresHealthPressureFact`：`availability`、`total_connections`、`active_connections`、`idle_connections`、`waiting_connections`、`max_connections`、`utilization`、`health`、`observed_at`、`source_status`。任何必需字段缺失/非法，整个事实收敛为 typed unavailable；不与第二个 Tool 拼接部分成功。

PostgreSQL definition 在保留既有 investigation 的同时增加 `service_health_pressure.v1`；API 投影、prompt profile 和 ToolRegistry 必须同时具有上表映射。connection-pool capability 与 Connector 使用同一个 Registry entry 的私有 DSN，不重新查 env。

既有 `explain_sql`、`show_index`、`show_create_table`、`check_lock_status` 是兼容慢查询路径，不属于 P12 统一 health intent，也不作为 P12 人工 Runner 输入。用户从现有工作台主动提交 SQL 时，仍只允许既有 SELECT/CTE 校验通过的 SQL，写语句在 connection 前拒绝；P12 不改变其公开能力。

### 5.2 端到端证据

deterministic fake 记录 binding 创建时的 opaque credential token、connector probe 和 Tool 调用，断言动态注册连接测试与 DBAgent capability 使用同一个对象 identity/service_id/token；token 只存在测试内存，不输出。API 测试覆盖：注册 → 连接测试 → 创建服务 Session → 接纳/执行 Run → ToolGateway → 唯一终态 → 安全 Trace/Result。

负向覆盖不存在 ID、类型不匹配、不属于 Session、注册后删除、意外 capability failure、ToolGateway timeout/late completion；都在外联前或 P11 接纳边界安全失败，无默认目标和第二结果。

## 6. S2：Redis 最小 Agent 只读调查

### 6.1 固定 capability

`RedisHealthCapability.read_health()` 无参数，内部固定调用且只调用：

1. `PING`
2. `INFO memory`
3. `CLIENT LIST`
4. `SLOWLOG LEN`

返回 `RedisHealthFact`：`availability`、`memory_bytes`、`client_connections`、`slowlog_count`、`observed_at`、`source_status`。CLIENT LIST 只在 capability 内计数后丢弃，不返回地址、name、cmd 或原始行；INFO 只提取 `used_memory`；SLOWLOG 不读取正文。

`redis_health_overview` Tool 无模型参数。`RedisServiceConnector.definition()` 把 `supported_investigations` 从空改为 `service_health_pressure.v1`；Connector snapshot 与 Tool capability 共享同一个固定 probe 实现，避免两份 Redis 命令清单。

### 6.2 failure 与禁止能力

外部失败封闭为 `not_configured`、`unavailable`、`timeout`、`permission_denied`、`cleanup_failed`，只带安全枚举和中性摘要。`cleanup_failed` 是“主调用没有形成可接纳事实且 cleanup 也失败”时的 failure code；若主调用成功但 cleanup 失败，保留事实但标记 `source_status=cleanup_unknown`。`cleanup_unknown` 只属于 source status，不是 failure code，且不得声称底层完全停止。

源码/行为双探针锁定四个命令和无参数 Tool schema；出现 `SCAN`、`KEYS`、`GET`、`MGET`、`EVAL`、`CONFIG`、`SET`、`DEL`、`FLUSH*`、任意 command 参数或原始结果透传时 P12 gate 失败。

## 7. S3：MySQL 最小真实只读接入

### 7.1 驱动、DSN 与资源边界

- 依赖唯一选择 `PyMySQL==1.2.0`。它是纯 Python、Python 3.9+、由 PyPI 标记 Production/Stable；SQLAlchemy 官方支持 `mysql+pymysql://`。不得同时引入 mysqlclient、mysql-connector-python 或异步驱动。
- 只接受 SQLAlchemy URL backend `mysql` 且 driver `pymysql`；拒绝裸 `mysql://`、MariaDB、其他 driver、缺失 username/host、fragment。首版要求 database path 为空，因为固定 GLOBAL SHOW 不需要默认库，且最低权限账号不应依赖库级权限；非空 database path 必须在外联前拒绝。
- URL query 参数采用空 allowlist：出现任何 query key 都拒绝，不做危险参数黑名单。timeout、`charset=utf8mb4` 与其他必要 driver 参数只由 factory 固定 `connect_args` 注入，DSN 不能覆盖；socket/unix socket、local infile、init command、client flags/multi-statements 等因此全部不可由 DSN开启。
- 密码可为空与否由目标账户策略决定，但 DSN 必须通过现有最小长度、加密和掩码纪律；验证错误不得回显 URL。
- `MysqlReadonlyCapability` 每次调用创建短生命周期 engine/connection，使用 `NullPool`；PyMySQL `connect_timeout=3`、`read_timeout=3`、`write_timeout=3`，固定 `charset=utf8mb4`。按“连接 3s + 每条 SHOW 最坏写 3s/读 3s × 2 + cleanup margin 1s”计算 whole-call 上界 16s，DBAgent 为该 binding 注入 18s ToolGateway 等待预算。
- 只执行固定 SHOW 语句，不发出 `SET`、事务控制或业务 SELECT。`finally` 顺序为 cursor/result close → connection close → engine dispose；各阶段独立捕获并映射 cleanup 状态，永不输出异常原文。

### 7.2 固定指标与最小权限

`MysqlHealthCapability.read_health()` 无参数，只执行下列固定语句：

```sql
SHOW GLOBAL STATUS WHERE Variable_name IN
  ('Uptime', 'Threads_connected', 'Threads_running', 'Slow_queries')
SHOW GLOBAL VARIABLES WHERE Variable_name = 'max_connections'
```

返回 `MysqlHealthFact`：`availability`、`uptime_seconds`、`current_connections`、`running_connections`、`max_connections`、`slow_query_count`、`observed_at`、`source_status`。字段必须为非负整数；缺失/重复/非数字行形成 typed unavailable，不猜值。

MySQL 8.4 官方文档说明 `SHOW STATUS` 与 `SHOW VARIABLES` 只要求能够连接，不需要额外权限。因此首版最低权限是专用账户仅具备登录/`USAGE`，不选择默认 database，不授予全局/库级 `SELECT`、`PROCESS`、`SHOW DATABASES`、`RELOAD`、`SUPER` 或任何写/管理权限。真实验收前人工核对账号由用户完成；Runner 不读取或打印 `SHOW GRANTS`。

禁止 `SHOW PROCESSLIST`、information_schema/performance_schema 查询、业务表 SELECT、任意 SQL、DDL、DML、事务控制、KILL、FLUSH、SET、文件和本地导入。源码 AST 与 fake driver 行为探针精确匹配固定语句集合和调用次数；另对非空 database、任意 URL query、socket/local-file/init-command/client-flag 输入做零外联负向探针。

### 7.3 Connector、API 与前端

- `MysqlServiceConnector` 复用 `ServiceConnector`，definition kind 为 `mysql`、supported investigation 为 `service_health_pressure.v1`；health snapshot 只把现有安全字段映射为 availability、client connections、slow query count，其余 MySQL 细节只进入 Agent typed fact，不扩展公开 API schema。
- `ALLOWED_KINDS`、API request validator、binding factory 和前端表单只增加 `mysql`。`kind` 公开字段仍是既有字符串；不新增 endpoint/field，不手改 generated OpenAPI 文件。
- 服务 API 已有 generic `supported_investigations` 投影；前端用它决定入口。ServiceCenter 增加 MySQL 选项与类型标签，Workbench 增加 `service_health_pressure.v1` 的固定提示模板，创建 Session/Run 时沿用当前卡片的精确 service_id。
- 后端 DBAgent 根据 Mysql binding 只注册 `mysql_health_overview`；如果 API 宣称 capability 但 factory/route/Tool 缺失，集成测试与 gate 失败。未知 capability 继续显示“未启用”。

`intent` 不是现有公开 API 字段，也不新增为字段；它是受控 UX template token，不是授权或后端安全参数。闭合链路为：

```text
Service API: service_id + supported_investigations
  → ServiceCenter 只为其中的 service_health_pressure.v1 生成链接
  → Workbench 以 (intent, service_id) 查精确本地模板
  → 模板只产生固定健康问题，创建的 Session 绑定原 service_id
  → Run 继续以 Session membership 校验该 service_id
  → Registry binding kind 决定唯一 capability/Tool 菜单
```

ServiceCenter 只会从 API 投影生成合法 token，并按现有流程先创建绑定当前 service_id 的 Session，再导航 Workbench。Workbench 收到被篡改/未知 intent、intent 不在该卡片投影中、缺失/被替换 service_id 时显示“调查能力不可用”，不自动填问句、不创建 Run；已经创建的空 Session 保持，不伪称能够回滚或阻止它。用户直接调用 API 提交自然语言时，后端不把文本中的 intent/服务名视为授权或目标；唯一目标仍是 Session/Run 的 service_id，唯一能力仍是该 binding 的封闭 Tool 菜单。前后端 contract test 对三个 kind 建立 `supported investigation → exact template → exact service_id → expected Tool name` 映射，并覆盖 tampered token 只保留空 Session、零 Run；删除任一环节即失败。

| kind | API investigation | Workbench 固定问句类别 | DBAgent 唯一 health Tool |
|---|---|---|---|
| postgres | `service_health_pressure.v1` | PostgreSQL 服务健康与连接压力概览 | `check_connection_pool` |
| redis | `service_health_pressure.v1` | Redis 服务健康与连接压力概览 | `redis_health_overview` |
| mysql | `service_health_pressure.v1` | MySQL 服务健康与连接压力概览 | `mysql_health_overview` |

### 7.4 最小 CHECK 迁移

新增唯一 `backend/migrations/versions/20260904_15_p12_mysql_service_kind.py`，revision 为 `20260904_15_p12_mysql_kind`（26 字符，不超过默认 `alembic_version.version_num` 32 字符边界），`down_revision` 为当前唯一 head `20260815_14_merge_p8_heads`，且只做：

```text
upgrade:
  service_registry_kind_valid
  kind IN ('postgres', 'redis')
  → kind IN ('postgres', 'redis', 'mysql')

downgrade:
  先 SELECT COUNT(*) FROM service_registry WHERE kind = 'mysql'
  count > 0 → raise RuntimeError，约束保持三类型，不修改任何记录
  count = 0 → 恢复两类型 CHECK
```

- SQLite 使用 `op.batch_alter_table("service_registry")` 在同一 batch 内 drop/create named constraint；其他支持的应用数据库使用 `op.drop_constraint()` + `op.create_check_constraint()`。
- upgrade/downgrade 都不新增/删除表、字段、索引，不回填、更新或删除行。ORM `ServiceRegistryRecord.__table_args__` 同步为三类型，避免 metadata 与迁移树漂移。
- migration test 从前一 head 建库，插入 PostgreSQL/Redis 行后 upgrade，断言数据逐字段保留且 MySQL 可插入；无 MySQL 时 downgrade 后两类数据仍逐字段保留、MySQL 插入被拒绝；有 MySQL 时 downgrade 抛出预期错误，记录与三类型约束均保留。
- 非 SQLite 分支不用真实外部数据库：以 deterministic Alembic operation spy/fake dialect 断言 upgrade 严格按“drop 同名 CHECK → create 同名三类型 CHECK”，downgrade 严格先查询 MySQL count，只有零记录才“drop → create 两类型 CHECK”；不得出现表/字段/数据 mutation operation。
- Alembic test 用 `ScriptDirectory.get_heads()` 断言恰好一个 head、revision ID 长度不超过 32，并运行完整 upgrade head / downgrade predecessor / re-upgrade head。测试只用临时 SQLite，不连接应用或外部数据库。
- 创建 Workpack 时必须重新 fetch 并证明 `20260815_14_merge_p8_heads` 仍是唯一 head；若 main 已出现新 revision/head，停止并回到 Design 更新 revision/down_revision，不自行创建 merge migration。

## 8. 凭据、failure、超时与 Trace

### 8.1 DSN 生命周期

动态 DSN 只以现有密文/nonce 落应用库；解密明文只在注册/启动装配调用栈中短暂存在，随后由 connector/capability 私有持有。binding、Agent、Tool 输入、Prompt、Run、事件、Result、Message、Trace、API、日志与截图都不得含明文 DSN、可还原目标、username、password、密文、nonce 或环境变量名。

静态 DSN 只由 `dependencies.py` 读取后进入相同 factory；Tool 永不再次查 env。P12 不新增 secret table、credential ID、lease、轮换或持久授权状态。

### 8.2 typed failure 与公开映射

内部 failure union：

| code | 语义 | 公开表达 |
|---|---|---|
| `binding_not_found` | service_id 不存在/已删除 | 目标不可用 |
| `binding_type_mismatch` | binding 与 Tool 类型不符 | 服务类型不匹配 |
| `investigation_not_supported` | capability 未启用 | 调查能力未启用 |
| `credential_unavailable` | 无法装配凭据 | 服务未配置 |
| `connection_unavailable` | 连接失败 | 服务不可用 |
| `operation_timeout` | Connector 操作超时 | 调查等待超时 |
| `permission_denied` | 最小只读读取被拒 | 只读权限不足 |
| `malformed_fact` | 返回结构不满足 typed fact | 服务事实不可用 |
| `cleanup_failed` | 无可接纳事实且 cleanup 失败 | 资源清理失败 |

Tool failure 经既有 `ToolExecutionResult`/ToolGateway 记录安全 code 与固定摘要；不得保存原始异常。若 failure 使 Runtime 不能形成诊断结果，继续由 P11 runtime guard 和现有 Run service 映射为公开 `DIAGNOSIS_FAILED`，不增加第二套公开错误协议。

ToolGateway 的三维语义保持 P11：`wait_status`、`acceptance_status`、`execution_status`。等待超时关闭结果接纳；未开始 future 可取消，已经运行且无法取消时只表达 `execution_status=unknown`，迟到事实/异常/audit 不再进入 Run。

为避免放宽同一 DBAgent 内其他 PostgreSQL Tool，`ToolGateway` 增加构造时注入的封闭 `timeout_by_tool: Mapping[str, float]`；`invoke()` 只按已经准入的 Tool 名查预算，未列出名称继续使用现有默认 3s，模型参数不能选择或覆盖 timeout。`BaseAgent` 仅透传该不可变 mapping；其他 Agent 和现有 PG 非 health Tool 不传 mapping，语义与默认值不变。service-bound DBAgent profile 精确配置：

| capability | resource 最坏串行预算 | Gateway wait |
|---|---:|---:|
| `check_connection_pool`（connect + read-only SET + 2 个固定 SELECT + cleanup） | 13s | 15s |
| `redis_health_overview` | 16s | 18s |
| `mysql_health_overview` | 16s | 18s |

每个底层 connect/operation 仍为 3s，cleanup margin 固定 1s；不共享一个小于串行上界的 3s Gateway。fake clock/阻塞 driver 分别覆盖边界前完成、resource timeout、Gateway timeout、运行中迟到与 cleanup margin；另断言 `explain_sql`、`show_index`、`show_create_table`、`check_lock_status` 及其他 Agent Tool 仍使用 3s。P12 不改变 P11 timeout 状态机，不声称同步数据库驱动被强杀，也不修复全局 Run deadline/cross-process cancellation gap。

### 8.3 Trace 与结果

RunEvent 只含既有角色、Tool 类别、固定状态、耗时和绑定 service_id；Tool 参数摘要不含 SQL/命令/连接参数。Result/Message 只包含经过 safe projection 的标量结论和真实来源类别，不含原始 Tool 输出。P11 的唯一终态、终态后隔离和迟到结果接纳规则保持不变。

## 9. P12 preflight 与人工 Runner

### 9.1 唯一 service_id validator

把当前注册命令的规则提取为唯一共享函数 `validate_service_instance_id()`：1–64 字符，正则 `^[a-z0-9][a-z0-9._-]*$`，返回 trim 后值。API request、application command、P12 preflight 和 Runner 全部调用它；禁止复制 P11 的更窄正则。

确定性探针正向覆盖数字开头、点号、下划线、连字符；负向覆盖空值、大写、非法字符和 65 字符。任何一处自行维护第二个正则时 P12 gate 失败。

### 9.2 软件 preflight

新增 `backend/scripts/check_p12_real_readonly_preflight.py`，只验证：

- `OPERMIND_P12_REAL_OPT_IN` 必须是精确 opt-in 值；
- 单一 `service_id` 存在并通过共享 validator；
- `credential_ref` 存在且语法为 `registry:<service_id>` 或 `env:<EXACT_VAR_NAME>`，registry ref 的 ID 必须与目标相同；env ref 只检查大写安全变量名语法，不从 service_id 派生变量名；
- service kind 必须显式为 postgres/redis/mysql；
- 运行环境不是 CI，且声明为非生产目标。

preflight 不解密、不读取 DSN 值、不导入网络 client、不连接数据库/Redis/模型，不打印 credential ref 的 env 名，不存储“已授权”状态。成功只输出“技术前置满足、尚未访问”。

### 9.3 独立非 pytest Runner

新增 `backend/scripts/run_p12_real_readonly_acceptance.py`，不被 pytest 收集；结构为：

1. 调用同一 preflight；
2. 要求交互式 TTY，并让用户当次输入精确 service_id 确认目标与只读范围；CI、非交互、确认不匹配均拒绝；
3. 从现有应用装配加载 Registry-internal binding，把输入 credential_ref 做固定前缀解析和 SHA-256 后，与 `BindingOrigin.source_fingerprint` 常量时间比较；动态 origin 由 `registry:<service_id>` 创建，静态 origin 由显式 bootstrap descriptor 的 env 名创建。比较不重读 DSN、不派生 env 名、不把 origin 交给 Agent，也不输出 credential_ref；
4. 注入 deterministic local scripted LLM/driver，固定选择该 binding 类型的健康 Tool；不构造外部模型 Provider；
5. 依次执行连接测试 → 创建服务 Session → 接纳并执行 Run → 读取安全 Result/Trace；
6. 输出仅含时间、service_id、kind、步骤状态、Run ID、终态和安全 failure code，不含目标地址、指标值、原始事实或异常；不清理目标数据。应用元数据证据保留在现有 Session/Run 表。

pytest 下只用临时 SQLite、fake binding、fake capability 和 scripted driver 验证 Runner orchestration；另覆盖 origin match、mismatch、不存在和所有失败输出不含 ref/env 名。`tests/conftest.py` 保持原字节/语义，真实 Runner 不作为 pytest escape hatch。三个真实目标分别运行一次，每次都需要新的用户明确授权。追加真实模型时另行确认 Provider 授权。

## 10. 测试、证据与阶段门

### 10.1 自动化分层

| 层级 | 事实来源 | 外联 | 主要证据 |
|---|---|---:|---|
| 单元/聚焦 | fake connector/capability/driver | 禁止 | binding、命令/SQL 固定集、failure、timeout、cleanup、脱敏 |
| API/前端 | 临时 SQLite + fake binding + MSW | 禁止 | CRUD、capability 投影、入口、intent/service_id 绑定 |
| 后端/前端全量与 CI | 全部 fake；conftest blocker | 禁止 | 无回归、即使存在真实 DSN 仍零外联 |
| preflight | 仅字符串/环境声明 | 禁止 | 缺条件失败关闭；成功仍“尚未访问” |
| 人工 Runner | 用户逐目标授权的 registry binding | 仅被授权目标 | 脱敏步骤与时间证据 |
| 可选真实模型 | 独立 Provider 授权 | 服务 + Provider | 与服务授权分离的补充证据 |

普通 pytest 继续由现有 `tests/conftest.py` 在导入应用前清除真实 DSN 并安装外联 blocker；P12 不要求它识别或修改新的 opt-in/credential-ref 标志。preflight/Runner 在 CI 或 `PYTEST_CURRENT_TEST` 存在时额外失败关闭，测试只把显式字典传给纯 `check_preflight()`，不从 pytest 进程环境启动真实链。不得以 marker、skip、monkeypatch 恢复、子进程或直接 DBAPI 导入绕过 blocker。真实 Runner 模块必须无 import side effect，能在禁止外联环境安全 import。

### 10.2 P12 exact-path gate

新增独立 `p12_stage_manifest.v1.json`、support verifier 和测试；manifest 固定用户确认后创建 Workpack 时的最终 base SHA、精确允许路径、依赖唯一增量、迁移 revision、允许服务类型和验证命令。

P12 gate：

- 比较 committed/staged/unstaged/untracked 四集合，路径必须是 manifest 的精确成员，禁止 glob；
- 调用 P10/P11 历史树 verifier，保持 baseline、generator、capability profile v1/v2、P11 manifest/gate 原字节与历史 SHA；不重算、不覆盖历史证据；
- 检查 `tests/conftest.py` hash/关键 blocker，不允许 skip/xfail/xpass、新真实访问 marker；
- 检查依赖只增加 `PyMySQL==1.2.0`；服务类型集合精确为 postgres/redis/mysql；
- 检查 Alembic 只有一个新 revision、单一 head，revision 精确为 `20260904_15_p12_mysql_kind`、长度 ≤32，且只替换 named CHECK；
- 检查无新 endpoint/公开字段、无生成 OpenAPI 手改、无第二 service_id regex；
- AST/行为负向探针拒绝任意 SQL、Redis 通用命令、写/管理操作、网络 client 暴露、Tool target 参数、凭据/异常泄漏和额外服务类型；
- 检查 API capability → Agent route/Tool → 前端入口完整，避免“UI 已启用但后端不可调查”。

### 10.3 实施验证矩阵

实施 Workpack 至少运行：

```powershell
# backend/
..\.venv\Scripts\python.exe -m pytest tests/test_p12_service_binding.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_p12_postgres_end_to_end.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_p12_redis_investigation.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_p12_mysql_connector.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_p12_migration.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_p12_preflight.py tests/test_p12_manual_runner.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_service_registration_api.py tests/test_postgres_connector.py tests/test_redis_connector.py tests/test_db_tools_real.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_contract_kernel.py tests/test_harness_runtime_adapter_contract.py tests/test_tool_gateway.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_regression_baseline.py tests/test_harness_zero_behavior_gate.py tests/test_harness_p11_stage_gate.py tests/test_harness_p12_stage_gate.py -q
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m ruff check .

# frontend/
npm run typecheck
npm run test
npm run build

# repo root
git diff --check
git status --porcelain=v1 --untracked-files=all
```

另运行 P12 gate 的负向临时树探针：删除 Redis/MySQL allowlist、加入禁用命令、复制 service_id regex、添加第四服务类型、加入 pytest escape、添加第二 migration/endpoint、泄漏 secret literal 时均必须失败。探针只改临时副本，不改工作树。

## 11. 文件级实施范围

下列为一个 Workpack 的精确上限；不需要的文件保持无 diff。用户确认 Design 后，Workpack 必须把实际路径收窄为 exact manifest，不得用目录或通配符。

### 11.1 生产与迁移

```text
backend/requirements.txt
backend/migrations/versions/20260904_15_p12_mysql_service_kind.py
backend/src/application/service_registration.py
backend/src/api/v1/dependencies.py
backend/src/api/v1/schemas.py
backend/src/domain/services.py
backend/src/infrastructure/persistence/models.py
backend/src/infrastructure/services/service_connector_factory.py
backend/src/infrastructure/services/postgres_connector.py
backend/src/infrastructure/services/redis_connector.py
backend/src/infrastructure/services/mysql_connector.py
backend/src/agents/db_agent.py
backend/src/tools/db_tools.py
backend/src/tools/service_health_tools.py
backend/src/core/agent.py
backend/src/core/bootstrap.py
backend/src/core/graph.py
backend/src/core/mock_runtime.py
backend/src/core/tool_gateway.py
backend/src/scenarios/db_diagnosis.py
frontend/src/features/services/ServiceCenterPage.tsx
frontend/src/features/workbench/WorkbenchPage.tsx
```

`core/agent.py` 只允许透传向后兼容的 per-tool timeout mapping；`core/tool_gateway.py` 只允许在不改变 P11 状态机/默认 3s 的前提下按已注册 Tool 名选择构造时固定预算；`scenarios/db_diagnosis.py` 只允许按 binding kind 生成与实际 Tool 菜单一致的 prompt/example。若实施发现无需 `core/graph.py` 或 `core/mock_runtime.py`，从 manifest 删除；不得为了占满 allowlist 修改。若现有 `ServiceRegistry` 无法从同一 connector entry 派生 binding view，停止并回到 Design；不得新建第二 registry。

### 11.2 scripts、测试、阶段证据与文档

```text
backend/scripts/check_p12_real_readonly_preflight.py
backend/scripts/run_p12_real_readonly_acceptance.py
backend/tests/test_p12_service_binding.py
backend/tests/test_p12_postgres_end_to_end.py
backend/tests/test_p12_redis_investigation.py
backend/tests/test_p12_mysql_connector.py
backend/tests/test_p12_migration.py
backend/tests/test_p12_preflight.py
backend/tests/test_p12_manual_runner.py
backend/tests/test_service_registration_api.py
backend/tests/test_postgres_connector.py
backend/tests/test_redis_connector.py
backend/tests/test_db_tools_real.py
backend/tests/test_harness_p12_stage_gate.py
backend/tests/support/harness_p12_stage_gate.py
backend/tests/fixtures/harness/p12_stage_manifest.v1.json
frontend/src/features/services/ServiceCenterPage.test.tsx
frontend/src/features/workbench/WorkbenchPage.test.tsx
frontend/src/test/handlers.ts
docs/design/service-center/P12-three-service-real-readonly-integration-design.md
docs/workpack/P12-three-service-real-readonly-integration/plan.md
docs/workpack/P12-three-service-real-readonly-integration/evidence.md
docs/workpack/P12-three-service-real-readonly-integration/review.md
docs/workpack/归档/P12-three-service-real-readonly-integration/plan.md
docs/workpack/归档/P12-three-service-real-readonly-integration/evidence.md
docs/workpack/归档/P12-three-service-real-readonly-integration/review.md
docs/workpack/README.md
docs/路线图.md
docs/prd/README.md
```

Workpack 路径只在用户确认 Design 后创建。P12 manifest 分成两个无通配集合：implementation 状态只允许 active 三文件；用户授权提交前的 closeout 状态只允许删除 active 三文件、创建 archived 三文件，并同步 `docs/workpack/README.md`、`docs/路线图.md` 与 `docs/prd/README.md` 的交付状态/索引，不得修改 PRD AC 或扩大范围。gate 不允许 active 与 archived 同时存在。测试优先新增 P12 文件；只有已有 contract 的兼容断言确需更新时才改列出的历史测试。

### 11.3 明确禁止修改

- `backend/tests/conftest.py`；P10/P11 baseline、generator、capability profile、manifest、gate/support 与归档 Workpack；
- P11 runtime safety、ToolGateway 的等待/接纳/底层状态语义及公开 Runtime contract；ToolGateway 只允许 §8.2 的 per-tool timeout 选择增量；
- 除唯一 P12 revision 外的全部历史迁移；
- 新公开 endpoint/field、OpenAPI 生成文件、应用数据库凭据模型；
- Action/Approval/Executor、PostgreSQL 靶场写能力、前端 API 直连、CI 外联配置；
- 任意新服务、通用 SQL/Redis/网络 Tool、真实目标夹具、secret 文件。

任何必要修改超出 §11.1–§11.2，停止并回到 Design/用户确认。

## 12. 兼容、回退与停止条件

### 12.1 兼容策略

- 公开 API 路径和字段不变；`kind=mysql` 是既有字符串字段的兼容扩展。
- PostgreSQL/Redis 静态 ID、动态记录、监控、服务会话、Run、mock 评测和 Tool 名称保持兼容；旧测试通过显式 fake binding 适配，不保留隐式全局 scenario。
- 现有 PostgreSQL/Redis 注册数据在 migration upgrade/downgrade 中逐字段保留。
- 服务中心 API 和前端都以 `supported_investigations` 为真相；无 capability 时入口禁用。

### 12.2 回退顺序

1. 暂停 MySQL 新注册和三服务健康 intent 的新入口，但保留当前后端读取能力；不删除任何记录。
2. 在仍保留 P12 backend/factory 的状态下检查 `service_registry`。存在 `kind='mysql'` 记录时立即停止整个回退，由用户另行决定数据保留策略；不得先移除 MySQL 代码/驱动，也不得自动修改记录。
3. 只有零 MySQL 记录时才执行 migration downgrade，恢复两类型 CHECK；随后回退前端入口、Agent Tool/capability、factory/binding 接线和 PyMySQL 依赖，恢复旧 PostgreSQL/Redis 行为。
4. 回退不覆盖 P10/P11 历史资产，不清理真实目标，不删除 Session/Run/Trace。

### 12.3 实施停止条件

出现以下任一项立即停止并报告：

- 需要第二张表、字段、数据回填、credential lease 或新的公开 API；
- 无法让三类服务共享唯一 binding，必须保留环境变量 Tool 读取或默认目标回退；
- MySQL 固定指标需要 `PROCESS`、业务表 SELECT、管理权限或任意 SQL；
- Redis 固定事实需要键空间/原始慢日志或通用命令；
- 必须削弱 `tests/conftest.py`、P10/P11 gate、断言或负向样例；
- 需要真实服务/模型才能让自动化测试通过；
- stage gate 不能用 exact path 或 Alembic 不能保持单一 head；
- 目标、凭据、异常或事实无法安全投影。

## 13. AC1–AC18 逐项映射

| AC | Design 决策 | 确定性/人工证据 |
|---|---|---|
| AC1 | §3 同一 factory/binding；PG Tool 不查 env | dynamic opaque token identity；PG API E2E |
| AC2 | §3.3 静态 env 仅 bootstrap，和动态共用 binding | 静态/动态参数化 contract |
| AC3 | §3.1/§5.2 双阶段校验，无 fallback | not-found/type/session/delete race 零外联探针 |
| AC4 | §5 PG 既有只读 capability + P11 唯一终态 | fake E2E；授权后 PG 人工 Runner |
| AC5 | §6.1 Redis typed fact 与无参数 Tool | exact fields/API/Result negative assertions |
| AC6 | §6.1–§6.2 唯一固定 probe | fake call ledger + AST allowlist mutation probe |
| AC7 | §7.3 API/UI 与 §7.4 最小 migration | CRUD/API/UI tests；migration 数据保留 tests |
| AC8 | §7.1 timeout/NullPool/cleanup/failure | fake DBAPI success/unconfigured/unreachable/timeout/permission/cleanup |
| AC9 | §7.2 fixed SHOW + 无 Tool 参数 | schema/AST/call ledger/forbidden SQL probes |
| AC10 | §8.2 P11 ToolGateway 三维接纳语义 | P11 regression + 三类 late result probes |
| AC11 | §8.1/§8.3 safe projection | secret corpus across logs/events/results/API/test output |
| AC12 | §10.1 conftest 保持、环境清理与外联 blocker | injected real-like env + full pytest zero-network probes |
| AC13 | §9.1–§9.2 共享 validator 与纯软件 preflight | ID 正负矩阵；每项缺失失败；成功“尚未访问” |
| AC14 | §9.3 独立 scripted Runner、逐目标授权 | fake orchestration；授权后三份脱敏人工证据 |
| AC15 | §10.3 全验证矩阵，P10/P11 历史门不变 | 聚焦/全量/前端/Ruff/diff/gates 全绿 |
| AC16 | §10.2 exact-path 与负向边界门 | 临时树 mutation probes 全部 fail-closed |
| AC17 | §6.1/§7.3 capability→API→UI→intent/service_id | 后端集成 + MSW UI routing/disabled tests |
| AC18 | §4 两个正交维度 | 2×2 装配 identity probes；scripted real-binding runner |

任何 AC 不能由上述确定性证据验证时，实施前回到 Design；不得通过 skip、xfail、放宽断言或删除负向样例制造通过。

## 14. 独立 Design Review 清单

Reviewer 只读检查下列问题，不修改文件：

1. 是否仍存在 env/registry、connector/tool、API/UI 的双事实源或默认目标回退；
2. mock 模型是否仍能隐式切换 service fact source；
3. pytest、preflight 或 Runner 是否形成真实访问逃生口；
4. service_id validator 是否有第二份规则或缩窄合法 ID；
5. binding/Trace/异常/Runner 是否泄漏凭据、目标或原始事实；
6. UI capability 与后端 route/Tool 是否可能半接入；
7. Redis/MySQL 是否开放任意命令、SQL、业务数据或额外权限；
8. migration 是否严格只替换 CHECK，数据与 downgrade 是否安全；
9. AC1–AC18 是否都有可重复的确定性证据；
10. 文件范围、回退和停止条件是否足以阻止 P12 扩张。

P0/P1/P2 必须在用户确认前全部修复；P3 也应尽量收敛或明确列为不阻塞遗留。

### 14.1 Review 结论

独立 Reviewer 全程只读完成四轮审查，最终结论 **PASS**：P0=0、P1=0、P2=0、P3=0。已关闭的主要问题包括 MySQL 空 database/空 query allowlist、PostgreSQL 固定 health 行为与完整 timeout 预算、credential origin 同源证明、Agent 窄 capability view、intent UX 语义、跨 commit 同 ID 可见性、per-ID poison 隔离、per-tool timeout、entry 暴露前 capability 校验、最小迁移 revision 长度/非 SQLite 证据，以及 active/archive 收口路径。Review 未修改文件、未访问真实目标。

保留但不阻塞 P12 的诚实边界：已开始 Run 持有旧进程内 binding，编辑/删除不构成实时 credential 撤销；同步 Tool 超时后底层停止状态仍可能未知；全局 Run deadline、跨进程取消、credential lease 与真实模型验收均不在 P12。没有需要用户在 Design 确认前继续裁决的未决架构问题。

## 15. 外部技术依据

- [PyMySQL 1.2.0（PyPI）](https://pypi.org/project/PyMySQL/)：固定版本、Python 要求与 Production/Stable 状态。
- [SQLAlchemy MySQL/PyMySQL URL](https://docs.sqlalchemy.org/en/20/core/engines.html#database-urls)：`mysql+pymysql://` driver 选择与 `NullPool` 用法依据。
- [MySQL 8.4 SHOW STATUS](https://dev.mysql.com/doc/refman/8.4/en/show-status.html)：语句只需连接能力，无额外权限。
- [MySQL 8.4 SHOW VARIABLES](https://dev.mysql.com/doc/refman/8.4/en/show-variables.html)：语句只需连接能力，无额外权限。
