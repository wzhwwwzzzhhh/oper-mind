# P11 Agent Harness 真实运行安全门 · 实施 Design

> 状态：独立只读 Review PASS，已于 2026-09-03 获用户明确确认；active Workpack 已在确认后创建
> 更新：2026-09-03
> Issue：[#121](https://github.com/wzhwwwzzzhhh/oper-mind/issues/121)
> PRD：[P11-harness-real-runtime-safety-gate.md](../../prd/agent-runtime/P11-harness-real-runtime-safety-gate.md)
> 上游基线：[P9-harness-contract-kernel.md](../../prd/agent-runtime/P9-harness-contract-kernel.md)、[P9 Harness 最终取舍](P9AgentHarness最终取舍与后续建议.md)

## 1. 决策结论与阶段边界

P11 只实施两个紧密切片：

1. **S1 Runtime 唯一终态与安全失败**：在 `RunApplicationService` 现有 Runtime 消费点前加入一个无持久化、无业务 writer 的 signal guard；继续由现有 Run/Result/Message/RunEvent/Proposal 事务承担唯一业务事实写入。
2. **S2 Tool / Connector 超时与真实验证前门禁**：区分等待、结果接纳和底层执行状态；取消尚未开始的排队 future，隔离已经运行 Tool 的迟到完成；用确定性探针复验既有 PostgreSQL/Redis 资源级限时、只读和脱敏；普通测试与 CI 默认禁止外部访问，并提供只做软件条件校验、不执行真实访问的 preflight。

本 Design 不进入 P12，不实际访问真实 PostgreSQL、Redis、模型 Provider 或其他外部资源，不创建 Task / Attempt / Context / Binding，不新增持久化、Recovery、全局 Run deadline、跨进程取消、公开 API、SSE、前端、迁移、服务类型、Connector、Tool、权限或动作语义。

## 2. 前置门、基线与工作区事实

### 2.1 需求与 Git 门

- 2026-09-03 已执行 `git fetch origin main`。
- `origin/main` 为 `602323899595e2db34876d6cfc2f47e38ae74096`，已包含正式路径 `docs/prd/agent-runtime/P11-harness-real-runtime-safety-gate.md`。
- PRD frontmatter 已核对为 `status: 已确认`、`phase: P11`、`issue: 121`。
- GitHub issue #121 为 OPEN，正文只含 S1/S2、开始门和排除项，没有平行子 Issue。
- `docs/workpack/` 只有归档目录；不存在 P11 active Workpack。本 Design 阶段不得创建。
- 当前 worktree 为 `D:/market-handsome/oper-mind`，分支 `codex/p11-harness-safety-gate`，检查时工作区干净。该分支 HEAD `f5ba8f313fd42e3062ac00a558a885ab7e3dc7f0` 与 `origin/main` 各自领先共同祖先 `c26336acc4e5b48362e1e979d150d2d3f8b37a98` 一个等价需求提交；`git diff origin/main` 为空。实施阶段不能把该历史关系误记为最终 base，必须从届时最新 `origin/main` 建独立 `codex/` 分支或 worktree，并记录完整 SHA。

### 2.2 当前 Runtime 主链

```text
RunApplicationService.execute_run
  → DiagnosisExecutor.stream(query, service_id)
    → CoordinatorDiagnosisExecutor
      → CoordinatorAgent.route_stream(query)
  → DiagnosisExecutionEvent 立即持久化
  → 最后一次 DiagnosisExecutionResult 被保留
  → _complete_success / _complete_failure 通过 Run CAS 写唯一业务终态
```

当前事实：

- `DiagnosisExecutor` 是唯一生产执行 port；`RuntimeAdapterContract` 仍是 P10 的框架无关 typed contract，不拥有 Run 状态。
- `RunApplicationService.execute_run()` 当前把每个非 event 对象当作 result，并覆盖前一个 result；流结束后只检查“至少一个 result”。因此零终止失败，但多个 result 取最后一个，result 后 event 仍会公开并持久化，非法对象可能延迟到 assembler 才失败。
- `CoordinatorDiagnosisExecutor` 只把显式 error 转成 `DiagnosisExecutionError`；factory、iterator、转换等意外异常仍可逸出。Run 外层 broad catch 最终会安全失败，但 Runtime 边界没有 typed failure 证据。
- `_complete_success()` / `_complete_failure()` 已以当前 Run 状态和 CAS 防止 `succeeded/failed/cancelled` 被迟到完成覆盖；这些方法和数据库仍是唯一业务 writer。
- 当前 Runtime port 没有 absolute deadline 或 `RuntimeControl`，阻塞或永不结束的 iterator 无法由 P11 中断。

### 2.3 当前 ToolGateway 与 Connector

- `ToolGateway` 每个实例持有一个 `ThreadPoolExecutor(max_workers=1)`。`future.result(timeout=...)` 超时后直接返回，既没有 `future.cancel()`，也没有表达结果接纳已关闭；文案“已中止”超过现有证据。
- 已经运行的同步 Tool 无法由 Python 安全强杀。当前迟到返回值不会由 `invoke()` 二次返回，但缺少 typed 状态和明确的迟到隔离契约；同一单线程池中后续排队 future 在超时后仍可能补执行。
- PostgreSQL engine 已设置 `connect_timeout=3` 与 `statement_timeout=3000`；只读 Tool/Connector 执行 `SET TRANSACTION READ ONLY`，DB Tool 已有非 SELECT 与非法标识符访问前拒绝逻辑。
- `PostgresServiceConnector.health_snapshot()` 会把连接/查询异常收敛为 unavailable，但 owned engine 的 `dispose()` 位于未保护的 `finally`，关闭失败仍可能逸出。
- Redis client 已设置 `socket_connect_timeout=3.0`、`socket_timeout=3.0`，只调用 `PING / INFO memory / CLIENT LIST / SLOWLOG LEN`；连接失败映射 unavailable，关闭失败只记录不含异常原文的 instance id。

### 2.4 P10 证据与本地执行条件

- P10 `current_capability_profile.v1.json` 诚实记录 `terminal_cardinality`、`unexpected_exception` 为 unsupported，ToolGateway timeout 为 expected gap。
- `zero_behavior_baseline.v1.json` 的首次提交、内容、生成器 raw/canonical hash 和 P10 capability v1 必须保持原字节；`harness_zero_behavior.py` 不得修改。
- P10 gate 当前仍以 HEAD 比较受保护生产文件，因此 P11 合法生产变化会使它失败。P11 必须把它改为验证 P10 交付提交 `4d17f6f65f616774b3b616faaed03348dd5a1c08` 的历史树，再由新的 P11 gate 验证当前变更；不能刷新 P10 baseline 或扩张 P10 全局 allowlist。
- 已尝试运行 P10 四套聚焦测试，但根 `.venv` 指向已不存在的 `C:/Users/35764/AppData/Local/Programs/Python/Python311/python.exe`，系统也没有可用 `python`。本阶段未重建环境，因为只授权 Design。实施 Workpack 开始门必须先按仓库规则恢复 Python 3.11 环境并复跑基线；不得修改 requirements/pyproject 迁就环境。

## 3. S1：Runtime 唯一终态与安全失败

### 3.1 唯一生产接线点

新增 `src.application.runtime_safety`，提供一个无状态的 `guard_runtime_stream(stream_factory)`。`RunApplicationService.execute_run()` 只把当前 `_stream_with_context(self._executor, ...)` 包进该 guard；不改生产 DI，不注册第二个 executor，不增加数据库、队列、checkpoint 或业务状态。

```text
唯一业务写路径

DiagnosisExecutor（现有唯一 port）
  → guard_runtime_stream（瞬时协议校验，无持久化、无 Run writer）
    → RuntimeEventSignal / RuntimeResultSignal / RuntimeFailureSignal
      → RunApplicationService（唯一接纳者）
        → 现有 Run CAS + Result / Message / RunEvent / Proposal 事务
```

`guard_runtime_stream` 复用 P10 的 `RuntimeEventSignal`、`RuntimeResultSignal`、`RuntimeFailureSignal` 和封闭 `FailureCodeValue`。它不实现 `RuntimeAdapterContract` 的 request/control/deadline 能力，也不伪装成新 Orchestrator。

### 3.2 有限流完整校验算法

guard 接收 `Callable[[], Iterator[object]]`，使 executor 调用、iterator 构造、迭代和信号转换都处于同一异常边界内。算法固定为：

1. 终止候选为空；合法 `DiagnosisExecutionEvent` 立即转换为 `RuntimeEventSignal` 并交给现有 Run 事件安全投影。
2. 首个 `DiagnosisExecutionResult` 转为 `RuntimeResultSignal`，但只缓存在内存中，不交给 Run service；首个合法 `RuntimeFailureSignal` 同样只作为终止候选。来自旧 port 的 `DiagnosisExecutionError` 映射为固定安全的 typed failure。
3. 出现终止候选后继续拉取 iterator 以证明有限流已经正常 EOF；候选未获得 EOF 证明前不得成功。
4. 候选后出现任何对象（第二 result/failure、event 或非法对象）立即形成协议 failure；该对象不向上游发出，已缓存 result 丢弃。failure 的交付不得依赖 iterator cleanup：guard 不在失败路径同步调用不受信任、可能无界阻塞的 `iterator.close()`，也不为 cleanup 新建后台线程或 callback；它只丢弃本地引用并立即交付 typed failure。底层 Runtime 自身资源释放仍由原 executor/iterator 的 `finally` 负责，无法证明会完成的 cleanup 明确保留为 deadline/cancellation gap。
5. 正常 EOF 且没有终止候选，形成 missing-terminal failure；正常 EOF 且恰有一个候选，才发出唯一终止 signal。
6. executor 构造、取 iterator、`next()` 或转换期间的非预期 `Exception` 映射为 unexpected-exception failure；不捕获 `KeyboardInterrupt`、`SystemExit`、`GeneratorExit` 等进程控制异常。
7. 未知对象形成 invalid-output 协议 failure，不把 `repr()`、类型详情、路径或原始数据写入 failure message。

终止类别与 P10 封闭 failure code 的映射：

| 内部场景 | P10 typed code | 固定安全文案 | 公开/持久化映射 |
|---|---|---|---|
| 正常 EOF 无终止、多终止、终止后输出、非法对象 | `internal.invariant_violation` | `诊断运行输出协议异常` | `DIAGNOSIS_FAILED` / `诊断执行失败，请稍后重试` |
| Runtime 构造、迭代或转换意外异常 | `runtime.unexpected_exception` | `诊断运行发生异常` | 同上 |
| 旧 port 主动抛 `DiagnosisExecutionError` | `model.execution_failed` | `诊断执行失败，请稍后重试` | 同上 |
| Runtime 主动给出合法 `RuntimeFailureSignal` | 保留其封闭 `FailureCodeId` | 按 code 重新生成固定安全文案，不信任上游 message | 同上 |

不扩展公开错误码；内部 code 只存在于进程内 signal 和行为测试，不写入 Run/RunEvent/API，也不记录原始异常。Run service 对 `RuntimeFailureSignal` 显式调用 `_complete_failure(run_id, *_safe_failure())`；剩余 Application/Persistence 异常继续由现有兜底处理。

### 3.3 唯一终态与完整业务一致性

- 只有 guard 在 EOF 后交出的唯一 `RuntimeResultSignal` 可调用 `_complete_success()`；result 候选不会提前组装、持久化或生成 proposal。
- Runtime failure 和所有协议违例都不得调用 assembler，因此没有 Result、成功助手消息或 Proposal。
- 已经公开的合法前置过程事件可以保留；终止候选后的对象绝不公开或持久化。
- `_complete_success()` / `_complete_failure()` 继续以 Run CAS 为最终权威。取消在 guard 阻塞、EOF 校验或 signal 交付期间获胜时，完成路径读取到 `cancelled` 后原样返回，不追加 Result/Message/Proposal 或第二终态事件。
- 测试同时统计数据库中的 Result、助手 Message、Proposal 和 `RUN_SUCCEEDED/RUN_FAILED/RUN_CANCELLED`，不能只断言返回 status。

### 3.4 明确保留的 deadline / cancellation gap

guard 为证明 result 是最后一项，必须继续读取到底层 iterator EOF。若 iterator 永不结束，或者在 result 候选后永久阻塞，P11 仍会等待；它不产生成功，也不假称已终止，但不会在本阶段自动失败。协议失败交付不等待不受信任的同步 `close()`；Runtime 自有 `finally`/cleanup 若阻塞或永不完成同样属于未解决的 deadline/cancellation gap。对应测试只用可释放的 `threading.Event` 建立边界，并在测试 `finally` 中释放桩，不遗留后台线程。

以下能力继续保留原状态：

- `deadline`：unsupported；
- `control`：externalized；
- `adapter_cancellation`：externalized；
- 阻塞 Runtime/Tool 的线程强杀、跨进程取消、全局 Run deadline：未实现。

## 4. S2：Tool 等待、接纳与底层执行事实

### 4.1 三维 typed 状态

`ToolInvocation` 保留既有 `status`、`detail`、时间与工具名，并新增仅供后端内部契约使用的三个封闭字段；`core.graph._tool_traces()` 继续只投影既有字段，所以 REST/SSE/OpenAPI 不变化。

| 维度 | 值 | 含义 |
|---|---|---|
| `wait_status` | `not_waited/completed/timed_out` | 调用方是否等待，以及等待是否到期 |
| `acceptance_status` | `not_applicable/accepted/closed` | Tool output/exception/audit summary 是否仍可被 Gateway 接纳 |
| `underlying_execution_status` | `not_started/completed/cancelled_before_start/stop_state_unknown` | 可被 future 证明的底层状态 |

映射固定为：

- 注册/参数阶段拒绝：`not_waited + not_applicable + not_started`；
- 限时内完成（含结构化 unavailable 和安全异常）：`completed + accepted + completed`；
- timeout 且 `future.cancel()` 返回 true：`timed_out + closed + cancelled_before_start`；
- timeout 且 `future.cancel()` 返回 false：`timed_out + closed + stop_state_unknown`。

`cancel()` 返回 false 时不通过 `done()`、读取 exception 或其他竞态观察把状态乐观升级为 completed；保守记录 unknown。只有 cancel 返回 true 才能声明尚未开始且不会补执行。

### 4.2 timeout 与迟到隔离

`ToolGateway.invoke()` 在 `FutureTimeoutError` 分支立即执行一次 `future.cancel()`，随后关闭本次结果接纳并返回唯一 timeout `GatewayResult`：

- 排队 future 取消成功后，线程池不得执行它；确定性测试用前一个 Event-blocking Tool 占满唯一 worker，再让第二个 Tool 排队并超时，断言第二个执行计数始终为零。
- 已运行 future 取消失败后允许底层线程自行结束和释放资源，但 Gateway 不注册 done callback、不读取其迟到 result/exception、不调用其迟到 `audit_summary()`，也不产生第二个 `GatewayResult`。
- BaseAgent 只接收到首次 timeout 的固定安全 output/record；释放阻塞 Tool 后，Agent memory、`_tool_invocations`、RunEvent 和公开 Trace 的已接纳内容保持不变。
- timeout 文案改为“等待超时，结果接纳已关闭”；运行中分支明确“底层停止状态未知”，不得出现“已中止/已停止/未产生访问”。排队取消成功分支可以准确陈述“排队执行已取消”。
- 测试以 `threading.Event` 建立 happens-before，只使用很短的 Gateway timeout 和宽松总上界，不用一秒级 `sleep` 猜调度。

`shutdown(wait=False)` 继续不强杀运行线程；可使用 Python 3.11 的 `cancel_futures=True` 取消尚未开始的剩余队列，但这不改变单次 timeout 必须显式 cancel 并记录结果的要求。

## 5. Connector 资源级保护的确定性证明

P11 不新增 Connector/Tool，也不调用真实资源。新增探针只注入 fake engine/client、记录构造参数和方法调用，并使用敏感哨兵验证结果、日志与 Trace。

### 5.1 PostgreSQL

机器证明必须同时覆盖：

1. `create_read_only_postgres_engine()` 固定 `postgresql+psycopg`、`connect_timeout=3`、`options=-c statement_timeout=3000`；Gateway timeout 不能替代这两层资源限时。
2. `PostgresServiceConnector` 和既有 DB Tool 在查询前执行 `SET TRANSACTION READ ONLY`；其后只出现既有 SELECT/EXPLAIN 读取。
3. `ExplainTool` 的非 SELECT/多语句输入、表/数据库非法标识符在 engine factory 调用前被拒绝。
4. engine factory/connect、只读事务设置、必需查询、结果转换或连接上下文退出失败时，没有可信快照，公开结果固定为 `unavailable`；若主流程已形成可信快照，随后仅 owned engine dispose 失败，则不篡改该快照，而以固定类别的内部 warning 表达 `cleanup_error`。若主流程本已失败，dispose 再失败仍保留首次 `unavailable`。为关闭当前 PostgreSQL dispose gap，`PostgresServiceConnector` 的 dispose 需要与 Redis close 相同的安全保护；两者日志都只含固定类别与 instance id，不含异常正文或 DSN。
5. 快照、Tool output、GatewayResult、caplog 和 RunEvent 不含 DSN、host、用户名、SQL 哨兵、异常哨兵或目标数据。

不修改 `postgres_engine.py` 或 `db_tools.py` 的既有行为；探针发现实际不满足上述事实时才回到 Design，不通过放宽 oracle 处理。

### 5.2 Redis

机器证明必须同时覆盖：

1. `Redis.from_url()` 固定 `socket_connect_timeout=3.0`、`socket_timeout=3.0` 和 `decode_responses=True`。
2. fake client 的调用序列精确等于 `ping/info("memory")/client_list/slowlog_len`，无键空间、写入、配置或任意命令入口。
3. 连接、命令、结果转换异常因没有可信快照而返回 `unavailable`；close 异常遵循与 PostgreSQL 相同的 finalizer 判据：保留此前已形成的可信快照（或此前已形成的 `unavailable`），另以固定类别 warning 表达内部 `cleanup_error`，日志只含固定文案和 instance id。
4. 序列化结果、日志和 Trace 不含 credential、DSN、host、用户名、原始异常或测试目标数据。

Redis 当前实现预计无需生产修改；若行为探针证明不符，只能在本 Design 重新 Review 后增加精确文件，不能临时扩 allowlist。

Connector 探针按下表形成确定 oracle，不把“公开服务状态”和“内部 cleanup 观察”混为一谈：

| 失败点 | 公开快照 | 内部可观察事实 | 禁止行为 |
|---|---|---|---|
| factory/connect、只读设置、必需 query/command、转换、连接上下文退出 | `unavailable` | 无原始异常的既有失败路径 | 不得返回部分 healthy 数据 |
| healthy 快照形成后的 owned dispose/close | 保留 healthy 快照 | 一条固定类别 `cleanup_error` warning | 不得覆盖快照、抛出或记录异常正文 |
| 主流程已 unavailable 后的 owned dispose/close | 保留首次 unavailable | 至多一条固定类别 `cleanup_error` warning | 不得用 finalizer 异常覆盖首次结果 |

P11 不给 ServiceSnapshot 增加字段，也不把 cleanup warning 暴露到 API/Trace；这里的 `cleanup_error` 是测试对安全日志类别的称呼，不是新公开状态或错误码。

## 6. 普通测试/CI 默认离线与真实测试软件前门

### 6.1 默认离线

`backend/tests/conftest.py` 在测试模块 collection（尤其 `src.app` 创建全局 services）前执行默认离线初始化。它先修改当前进程环境，因此此后普通测试创建的子 pytest/子进程默认继承同一安全环境；专门的负向测试若构造带哨兵的子进程，也必须在子进程 collection 前再次执行同一初始化：

- 删除所有已存在的 `OPERMIND_SERVICE_*_DSN` 与 `OPERMIND_SERVICE_*_LOG_DIR`，从而同时关闭动态服务连接、受管真实日志目录和由 `postgres-target` DSN 隐式开启的 target action 模式；
- 把旧入口 `OPERMIND_PG_DSN`、`OPERMIND_KNOWLEDGE_DIR` 显式覆盖为空，以压过 `config.local.yaml` 中可能存在的 `services.pg_dsn`/`knowledge.directory`；把 `OPERMIND_APP_DATABASE_URL` 覆盖为测试进程专属的临时 SQLite URL，以压过本地真实元数据库；
- 固定 `OPERMIND_API_KEY=mock`、`OPERMIND_BASE_URL=http://mock.invalid`、`OPERMIND_MODEL=mock`，压过本地真实模型 Provider 配置。测试用例仍可在用例内通过 monkeypatch 设置哨兵值，但访问侧必须同时注入 deterministic fake；不得靠恢复真实环境通过。

初始化后再安装测试期外部访问拒绝器：Python DNS/socket 连接失败关闭；非 SQLite SQLAlchemy Engine 的真实 `connect()` 失败关闭；Redis 的真实命令发送失败关闭；模型 Provider 的真实 transport 失败关闭。对文件系统不做会破坏解释器/依赖加载的全局 `open()` 劫持，而是在现有两个资源入口（日志 `LogSourceConnector` 与知识 `SearchKnowledgeTool`/reader）安装测试 guard：只有仓库 fixture 和 pytest 临时目录中由测试显式创建的路径可读，其他已配置绝对目录在首次 `resolve/is_dir/glob/open` 前以固定错误失败关闭。临时 SQLite、FastAPI TestClient、httpx MockTransport 和注入 fake 不受影响。所有拒绝异常只含固定 `OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED`，不含目标、路径或凭据。

新增两层负向证明：

1. 启动子 pytest 时注入 service DSN、`*_LOG_DIR`、knowledge dir、旧 PG DSN、真实应用数据库 URL 和模型哨兵，并让 `config.local.yaml` 等价 fake 提供剩余入口；collection 后断言这些入口全部解析为 disabled/mock/临时 SQLite，target action 为 mock，子进程继承值也保持安全。
2. 对 DNS、socket、非 SQLite DB、Redis、模型 transport、真实日志目录和真实知识目录分别安装“被调用即失败”的计数哨兵，运行普通 API/全量入口后计数均为零；另用仓库 fixture/pytest 临时目录和注入 fake 证明合法离线测试仍可执行。

CI 已执行 `pytest tests -q`，因此复用同一门禁；不新增 skip、marker 绕过、环境白名单或 CI 专用旁路。若某个真实入口无法在 `conftest.py` 的测试边界内阻断，必须停止并回到 Design，不能修改生产配置语义来迁就测试。

### 6.2 只做技术条件校验的 preflight

新增 `backend/scripts/check_p11_real_resource_preflight.py`，它自身不导入数据库/Redis/HTTP 客户端，不解析或输出凭据正文，不执行 DNS、socket 或资源访问。它只验证：

1. 显式 opt-in 精确为约定值；
2. 显式提供非空目标 service id；
3. 显式提供 credential 环境变量**引用名**，引用名必须与目标的 `OPERMIND_SERVICE_<NORMALIZED_ID>_DSN` 一致，且当前进程中该引用非空。

缺少或不匹配任一条件时，在任何注入 probe 被调用前抛出封闭 SafeStop code；输出不含目标连接细节或凭据。全部软件条件满足时只返回：`technical_prerequisites=satisfied`、`external_access_performed=false`、`human_authorization=required`，不运行真实测试。

用户对目标、账号权限、数据边界、脱敏方式和清理范围的**当次授权**不建模为环境变量、仓库文件、永久开关或自动通过状态。未来真实 runner 必须在本 preflight 之后另设一次人工操作门；P11 实施与验收不会触发该 runner。

## 7. P10 历史证据与独立 P11 阶段门

### 7.1 P10 历史门

`zero_behavior_baseline.v1.json` 与 `harness_zero_behavior.py` 原字节不变。`test_harness_zero_behavior_gate.py` 保留全部负向断言，但把“当前 HEAD 必须仍是 P10 零行为包”的阶段性判断改为：

- 从 Git 对象读取 P10 交付提交 `4d17f6f65f616774b3b616faaed03348dd5a1c08`；验证依赖、受保护生产文件、API/迁移/前端聚合 hash、P10 diff allowlist 与 baseline 一致；
- 对该历史树运行 P10 import-boundary 检查，证明 P10 当时未激活 contract；
- 继续在当前树验证 baseline 首次提交内容、generator raw/canonical hash、v1 profile 不可改以及 profile 版本连续；
- 保留越界路径、生产 import、声明漂移和 skip/xfail 的负向样例，不删除或放宽断言。

P10 gate 不再决定 P11 当前生产路径是否允许变化，也不把 P11 路径加进 P10 全局 allowlist。

### 7.2 P11 阶段声明与 gate

实施 Workpack 在最终 base 确认后新增 `p11_stage_manifest.v1.json`，精确记录：

- 最终完整 `origin/main` base SHA；
- 本 Design §8 的 exact path allowlist；
- 禁止目录与依赖/OpenAPI/Alembic hash 预期；
- P10 delivery SHA、baseline 首次提交 blob SHA 与 generator canonical SHA；
- v1 profile SHA、要求新增连续 v2 profile；
- P11 测试/support 的零 skip/xfail 列表。

新的 `harness_p11_stage_gate.py` 和 `test_harness_p11_stage_gate.py` 必须检查 committed/staged/unstaged/untracked 四集合，任何未列路径均失败；不接受 `backend/**`、`docs/**` 或全仓通配前缀。它还要验证：

- P10 baseline/generator/v1 profile 未变，P10 历史门可复验；
- 依赖、迁移、API/OpenAPI/SSE、前端、生产 DI、服务/Tool 注册集合、固定动作文件无变化；
- 只有 `RunApplicationService` 可以从生产链消费 Runtime guard，guard 无持久化/Connector/Tool/Agent/API import；
- `ToolGateway` 仍是 Agent 唯一工具执行入口；
- 新增 P11 测试/support 无 skip、xfail/xpass/importorskip，仓库既有 inventory 不增长；
- active Workpack 路径与归档路径严格互斥；Design 确认后且实施未归档时 active P11 Workpack 精确为一份，归档后 active 路径必须消失且归档精确为一份，任何双份、零份（实施期间）或第二个 P11 active Workpack 都失败；
- 只改 capability fixture、删除 gap 或移除负向样例不能通过行为 probe。

## 8. 实施允许文件与禁止文件

### 8.1 唯一允许上限

Design 确认后的 P11 manifest 只能列入以下精确文件；实际不需要的文件保持无 diff：

```text
backend/src/application/runtime_safety.py
backend/src/application/services.py
backend/src/core/tool_gateway.py
backend/src/infrastructure/services/postgres_connector.py
backend/scripts/check_p11_real_resource_preflight.py
backend/tests/conftest.py
backend/tests/fixtures/harness/current_capability_profile.v2.json
backend/tests/fixtures/harness/p11_stage_manifest.v1.json
backend/tests/support/harness_p11_contracts.py
backend/tests/support/harness_p11_stage_gate.py
backend/tests/test_harness_p11_runtime_safety.py
backend/tests/test_harness_p11_tool_connector_safety.py
backend/tests/test_harness_p11_stage_gate.py
backend/tests/test_harness_zero_behavior_gate.py
docs/design/agent-runtime/P11AgentHarness真实运行安全门实施Design.md
docs/workpack/P11-harness-real-runtime-safety-gate/plan.md
docs/workpack/P11-harness-real-runtime-safety-gate/evidence.md
docs/workpack/P11-harness-real-runtime-safety-gate/review.md
docs/workpack/归档/P11-harness-real-runtime-safety-gate/plan.md
docs/workpack/归档/P11-harness-real-runtime-safety-gate/evidence.md
docs/workpack/归档/P11-harness-real-runtime-safety-gate/review.md
docs/workpack/README.md
```

active 与归档 Workpack 路径是互斥生命周期位置，不允许同时保留两份。当前 Design 阶段只允许第一份 Design 文档，不创建上述 Workpack 或代码文件。

### 8.2 明确禁止

- `backend/tests/fixtures/harness/zero_behavior_baseline.v1.json`、`backend/tests/support/harness_zero_behavior.py`、`current_capability_profile.v1.json`；
- `backend/src/application/contracts.py`、`runtime_contracts.py`、生产 DI `api/v1/dependencies.py`、`app.py`；
- `backend/src/infrastructure/services/postgres_engine.py`、`redis_connector.py`、`backend/src/tools/**`、固定动作/collector 文件；
- `backend/migrations/**`、`backend/src/api/**`、`frontend/**`、依赖/lockfile、`.github/workflows/**`；
- P12、真实 E2E、凭据文件、日志/截图/证据中的真实目标数据。

如实现证明必须修改禁止文件，立即停止并回到 Design/用户确认，不能扩 allowlist 后继续。

## 9. 两个实施切片与顺序

### S1 Runtime 唯一终态与安全失败

1. 新增 Runtime guard 与单元行为 probe；
2. 在 `RunApplicationService` 唯一消费点接线，并补 Result/Message/Event/Proposal/CAS 集成断言；
3. 新增 capability v2：只把 `terminal_cardinality`、`unexpected_exception` 升级为 `mapped`，其余 capability 按行为探针维持真实状态；
4. 复跑 P10 Runtime/Run/取消/Trace/固定动作回归。

### S2 Tool / Connector 与真实验证前门

1. ToolGateway 增加三维状态、排队 cancel 和迟到接纳关闭；
2. 修复 PostgreSQL owned-engine dispose 安全收敛；以 fake 复验 PostgreSQL/Redis 限时、只读、命令集和脱敏；
3. 建立 pytest collection 前默认离线门和纯 preflight；
4. 建立 P10 历史门转换与独立 P11 manifest/gate，集中复验全量。

没有第三个隐含切片；若默认离线门暴露现有测试真实依赖，先把该用例改成确定性 fake，但只能在本 Design 允许的测试文件内完成。命中其他文件则暂停并 Review。

## 10. 验证矩阵与命令

实施阶段至少运行：

```powershell
# backend/
..\.venv\Scripts\python.exe -m pytest tests/test_harness_p11_runtime_safety.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_p11_tool_connector_safety.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_contract_kernel.py tests/test_harness_runtime_adapter_contract.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_tool_gateway.py tests/test_agent_gateway.py tests/test_postgres_connector.py tests/test_redis_connector.py tests/test_db_tools_real.py tests/test_db_lock_pool_tools.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_regression_baseline.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_zero_behavior_gate.py tests/test_harness_p11_stage_gate.py -q
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m ruff check .

# repo root
git diff --check
git status --porcelain=v1 --untracked-files=all
git diff --name-only <P11-final-base>...HEAD
git diff --cached --name-only
git diff --name-only
git ls-files --others --exclude-standard
```

阶段门还必须计算并比较 P10 baseline/generator/v1 profile SHA，检查 normalized OpenAPI 与 Alembic heads，扫描 skip/xfail/xpass、敏感字面量、凭据文件名、真实目标/网络调用以及 exact path 范围。禁止以 `skip`、`xfail`、放宽断言、删除负向样例或重算 baseline 通过。

## 11. AC1–AC19 逐条映射

| AC | 实施与机器证据 |
|---|---|
| AC1 | 正常 event* + result 经 EOF 后只交出一个 result；Run 集成测试精确统计一个 Result、一个 assistant Message、一个 succeeded 状态和一个 RUN_SUCCEEDED。 |
| AC2 | empty iterator → `internal.invariant_violation`；集成断言 failed 且 Result/成功 Message/Proposal 为零。 |
| AC3 | result+result、result+event、failure+任意输出均失败关闭，候选 result 和终止后对象不提交；独立永不结束桩只证明不会提前成功，并继续标记 deadline gap，不等待其自然结束。 |
| AC4 | stream factory、取 iterator、next、转换四处异常均转 `runtime.unexpected_exception` 固定文案；序列化、Run/Event、caplog/API 哨兵扫描无原始异常/路径/SQL/Prompt/Tool output/credential。 |
| AC5 | 合法 `RuntimeFailureSignal` 的封闭 code 在 guard probe 中保留，message 重建；Run/Event/API 只见 `DIAGNOSIS_FAILED` 和固定安全文案，失败终态事件唯一。 |
| AC6 | Event 控制取消与完成竞态；分别让 cancel/result/failure 迟到，CAS 后快照不变，终态事件总数一且无迟到 Result/Message/Proposal。 |
| AC7 | v1 不改、新增连续 v2；独立 P11 probe 证明 terminal/unexpected 为 mapped，声明突变负向样例失败；deadline/control/adapter_cancellation gap 原样保留。 |
| AC8 | Event-blocking running Tool 在短 timeout + 容差上界内返回唯一 timeout；文案与 record 不声称停止。 |
| AC9 | timeout 后释放返回敏感 output、抛敏感异常、变更 audit summary 三场景；Agent memory、GatewayResult、invocation list、RunEvent/Trace 序列化均无哨兵且无第二结果。 |
| AC10 | 前一 Tool 占满 worker，第二 Tool 排队超时；`future.cancel()==true`、状态 `cancelled_before_start`，释放前一 Tool 和 shutdown 后第二执行计数仍为零。 |
| AC11 | cancel true/false 两场景分别记录 `cancelled_before_start`/`stop_state_unknown`；只有可证明场景表达取消，unknown 不被命名为 stopped/cancelled。 |
| AC12 | fake engine 精确断言 connect/statement timeout、只读事务、SELECT/EXPLAIN；非 SELECT/多语句/非法标识符访问前拒绝；主流程失败为 unavailable，finalizer 失败保留首次快照并只留固定 `cleanup_error` 类别；DSN/异常哨兵不进入结果/Trace/log。 |
| AC13 | fake Redis factory 精确断言两类 timeout 和命令序列；连接/命令失败为 unavailable，close 失败保留首次快照并只留固定 `cleanup_error` 类别；credential/DSN/host/异常/目标数据不进入结果/log/Trace。 |
| AC14 | collection 前净化 service DSN/log dir、knowledge、旧 PG、应用 DB、模型与 target action 入口，并让子进程继承；网络/非 SQLite DB/Redis/模型及真实日志/知识目录拒绝器运行普通/全量入口时调用计数均为零；CI 复用全量命令。 |
| AC15 | preflight 分别缺 opt-in、target、credential ref、引用值及引用不匹配，均在 fake access callback 前 SafeStop；通过态仍标记 `human_authorization=required` 和 `external_access_performed=false`。 |
| AC16 | 新 P11 套件覆盖 PRD 列出的全部负向场景；P11 stage gate 扫描新旧 skip/xfail/xpass inventory，测试自身全绿。 |
| AC17 | P10 Contract Kernel、Runtime Adapter、ToolGateway contract、Run/取消/Trace/固定动作 baseline、合法 mock 双跑与后端全量命令全部通过。 |
| AC18 | P11 exact four-set gate + hash/AST/注册集合检查证明无迁移、API/OpenAPI/SSE、前端、依赖、新 service/Connector/Tool、权限或真实网络变化。 |
| AC19 | P10 baseline、generator、v1 profile 原 blob/hash；P10 历史树门与 P11 manifest/gate 分离；重算历史文件、删除负向断言、通配 allowlist 或越界生产路径的测试负向样例均失败。 |

## 12. 回退、风险与停止条件

### 12.1 回退

- S1 回退：移除 `RunApplicationService` 对 guard 的单一调用并删除新增 guard；现有 `DiagnosisExecutor`、DI 和数据库事实模型无需迁移或数据回退。
- S2 回退：还原 ToolGateway 三维记录/cancel 分支与 PostgreSQL dispose 保护，删除默认离线/preflight/P11 gate 工件；不存在后台 callback、持久化 ToolCall 或外部状态需要清理。
- P10 历史资产从未改写，回退 P11 后仍可从 P10 delivery commit 原样复验。

回退只能通过正常反向 diff 并重新跑 P10/P11 回归，禁止 `git reset --hard`、覆盖 baseline 或删除用户/其他 Agent 改动。

### 12.2 主要风险与控制

| 风险 | 控制 |
|---|---|
| 为校验 EOF 缓存 result 导致无限流等待 | 不提前成功；明确保留 deadline gap，不在 P11 虚构 deadline。 |
| guard 成为第二 Run/Adapter 事实源 | 无 ID、状态、存储、writer、DI；只发 P10 signal，由现有 Run service 唯一接纳。 |
| typed failure 泄露上游正文 | 只保留封闭 code，message 固定重建；公开统一 `DIAGNOSIS_FAILED`。 |
| cancel 与 future 完成竞态被乐观解释 | cancel false 一律 unknown；不读取迟到值或异常。 |
| 单 worker 被运行中超时 Tool 占用 | 后续排队超时必须 cancel；运行中停止未知保留为 gap，不承诺吞吐或强杀。 |
| 全局测试离线门破坏确定性 mock | 允许 SQLite、TestClient、MockTransport 和显式 fake；无绕过 marker，冲突必须显式修测试注入。 |
| P10 gate 被弱化以容纳 P11 | 固定 P10 delivery Git 对象和全部历史 hash/负向断言；P11 单独 exact manifest。 |

### 12.3 必须停止并回到用户确认的条件

- 需要修改 §8.2 任一禁止文件或扩展 exact allowlist；
- 需要新迁移、公开 API/SSE/前端/依赖、Connector/Tool/服务/权限；
- 需要 Runtime/Tool 全局 deadline、线程强杀、跨进程取消、queue/worker、Recovery 或 exactly-once；
- 需要实际连接、探测、读取、写入或清理任何真实外部资源；
- 默认离线门无法在不修改范围外测试/生产入口的情况下建立；
- 行为 probe 与 capability v2 不一致，或者只能通过改声明、删 gap/负向断言才能通过。

## 13. 未决问题与授权状态

本 Design 没有需要扩大 P11 产品范围的未决问题。实现中允许调整测试函数名和纯内部 helper 名，但不得改变算法、状态语义、AC oracle、exact 文件上限或排除项。

独立只读 Review 已完成且最终结论为 **PASS**，P0–P3 无剩余发现；Reviewer 全程未修改文件。首轮发现与关闭情况：

1. P1 默认离线未完整覆盖资源型本地配置：已补全 DSN、日志/知识目录、旧 PG、应用数据库、模型、target action、子进程继承和文件入口 oracle。
2. P1 Connector close/dispose 语义不清：已用统一状态表区分主流程 `unavailable` 与 finalizer `cleanup_error`，并固定公开快照和安全日志行为。
3. P2 iterator cleanup 可能阻挡 typed failure：已规定失败交付不等待同步 `close()`，阻塞 cleanup 诚实归入 deadline/cancellation gap。
4. P2 active/归档 Workpack 只有文字互斥：已加入 P11 stage gate 的唯一性与互斥机器断言。

当前已完成：需求门核验、issue 阅读、代码/测试/基线静态审计、实施 Design、独立只读 Review 与全部 Review 修复。当前未完成且未获授权：active Workpack、最终实施 base、任何生产代码与测试实现。下一步必须等待用户明确确认本 Design。
