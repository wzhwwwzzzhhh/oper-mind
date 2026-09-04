# P11 Agent Harness 真实运行安全门 · 实施证据

> 状态：active；S1/S2 实施、最终全量验证与独立只读 Review 均 PASS，待用户验收
> 最终 base：`602323899595e2db34876d6cfc2f47e38ae74096`

## 前置证据

- `git fetch origin main` 后 `origin/main` 精确为最终 base。
- PRD frontmatter 已确认：`status: 已确认`、`phase: P11`、`issue: 121`。
- Design 独立只读 Review PASS；用户已明确确认。
- 分支 `codex/p11-harness-real-runtime-safety-gate` 从最终 base 创建。
- 当前没有真实资源访问；所有后续验证限定 deterministic fake/mock。
- 原根 `.venv` 已可恢复地移至忽略目录 `.tmp/p11-broken-venv-backup`；使用 Codex bundled Python 3.12.13 按未修改的 `backend/requirements.txt` 重建根 `.venv`。
- 在子进程移除 `OPERMIND_SERVICE_*`、强制 mock 模型并使用临时 SQLite 后运行 P10 Contract Kernel、Runtime Adapter、ToolGateway、AgentGateway 与 regression baseline：`75 passed in 12.03s`。

## AC1–AC19

| AC | 可重复证据与结论 |
| --- | --- |
| AC1 | `test_harness_p11_runtime_safety.py` 的有限流/Application 探针证明：事件可流式通过，result 仅在正常 EOF 后接纳；只有一个 Result、成功 Message、`succeeded` 终态和终态事件。 |
| AC2 | 零终止探针输出 `internal.invariant_violation`；Application 断言无 Result、成功 Message 或 Proposal，公开失败为 `DIAGNOSIS_FAILED`。 |
| AC3 | 多终止、终止后事件及终止候选后再抛 typed error 的负向探针均归为 `internal.invariant_violation`；第一终止信号不会被提前写入，迟到事件不会公开；无限/阻塞 iterator 仍为 deadline gap。 |
| AC4 | factory、`iter()`、`next()` 和 signal conversion 异常探针均封闭为 `runtime.unexpected_exception`，固定文案不含原始异常、堆栈或敏感输入。 |
| AC5 | 合法 `RuntimeFailureSignal` 保留封闭内部 code 供探针断言，Application 仅持久化既有 `DIAGNOSIS_FAILED` 与安全文案，唯一失败终态。 |
| AC6 | result/failure 与 cancel 竞态探针证明既有 CAS 保留 cancelled 终态，终态事件总数为一，无迟到 Result、Message 或 Proposal。 |
| AC7 | `current_capability_profile.v2.json` 仅将 `terminal_cardinality` 和 `unexpected_exception` 提升为 mapped；profile 校验会直接运行 guard 多终止与意外异常探针，不接受调用方布尔自证；`deadline`、`control`、`adapter_cancellation` 等 gap 保留。 |
| AC8 | ToolGateway 确定性超时探针断言唯一 timeout；worker 用 tagged outcome 将 Tool 自身 `TimeoutError` 与 Gateway 等待到期分离；公开摘要不声称底层已中止。 |
| AC9 | 运行中 Tool 在 timeout 后返回敏感 output、抛敏感异常或生成 audit summary 的探针证明：Gateway 不再读取 future，Agent memory/trace 无迟到内容，无第二个 result。 |
| AC10 | 单 worker 被前调用占用时，第二个排队 future 超时后 `cancel()` 成功，释放 worker 后执行计数仍为零。 |
| AC11 | 未开始 future 记为 `cancelled_before_start`；已运行且不能取消时记为 `stop_state_unknown`。并发 shutdown 取消排队 future 的 `CancelledError` 明确映射为 `completed/closed/cancelled_before_start`，不误报底层已完成。 |
| AC12 | PostgreSQL fake 断言 connect/statement timeout 配置、read-only transaction、SELECT-only/标识符校验、异常和 DSN 脱敏；owned-engine dispose 失败也安全收敛。 |
| AC13 | Redis fake 断言 connect/socket timeout、允许命令集不扩大、连接/命令/关闭失败安全收敛；命令与 close 双失败仍保留首次 unavailable，凭据不进入 result/log/trace。 |
| AC14 | `tests/conftest.py` 在 collection 前移除所有 `OPERMIND_SERVICE_*_DSN/*_LOG_DIR`，强制 mock model 与 session 唯一临时 SQLite；全进程 blocker 在测试模块导入前安装，拒绝 `getaddrinfo/gethostbyname/gethostbyname_ex/gethostbyaddr/getnameinfo`、所有 INET 连接（含 loopback/`connect_ex`/UDP `sendto`）、非 SQLite SQLAlchemy、Redis、真实 HTTP transport 和越界文件读取；仅允许 Python 内部 `socketpair`，且 blocker 保持到进程退出。 |
| AC15 | `check_p11_real_resource_preflight.py` 缺 opt-in、service id、credential env reference 或引用值时均在访问前 fail-closed；成功仅声明技术条件满足、`external_access_performed=false`、`human_authorization=required`。 |
| AC16 | 新增所有要求的负向样例；P11 stage gate 用 P10 AST inventory 扫描直接、别名、decorator、module/param mark 形式的 skip/xfail，并用显式 required-probe inventory 拒绝删除必备负向样例。 |
| AC17 | P10 Contract Kernel、Runtime Adapter、ToolGateway/AgentGateway、Run/取消/Trace/固定动作、Connector、regression baseline 与 P10/P11 gate 显式合并回归 `197 passed`；后端全量 `769 passed`。 |
| AC18 | P11 stage gate 对 committed/staged/unstaged/untracked 四集合作 exact-path 校验，同时锁定依赖、API/OpenAPI/SSE、Alembic/迁移、前端、服务/Connector/Tool 注册集、网络客户端和权限边界。 |
| AC19 | P10 baseline/generator/v1 profile 原字节 hash 保持，P10 改为从历史 delivery tree 复验；P10 全 7 项门禁用例纳入 inventory，其中两个关键负向函数由统一换行后的完整函数源码 SHA 锁定，避免 Python 3.11/3.12 AST 表示差异且不降低内容约束。P11 manifest 仅允许 Design exact paths，active/archive 是代码固定非空 3+3 互斥集合；通配、重算 baseline、清空 Workpack、删负向断言或越界均有拒绝探针。 |

## 验证日志

- P10 实施前回归：`75 passed in 12.03s`。
- S1 最终聚焦：`25 passed in 12.75s`。
- S2 自审修复后聚焦：`24 passed`（已包含并发 shutdown 取消探针）。
- P10/P11 自审修复后阶段门：`19 passed`（已包含 DNS/生命周期削弱反例）。
- Reviewer 指定的 loopback 服务注册/API 路径：`16 passed, 1 warning in 28.13s`。
- Contract Kernel + Runtime Adapter + ToolGateway/AgentGateway + Connector + regression + P10/P11 gate（含 S1/S2），自审修复后显式复跑：`203 passed, 2 warnings in 42.58s`。
- 独立只读 Review 与自审修复后复核：均 PASS，P0/P1/P2/P3 无剩余；Reviewer 未修改文件、未访问真实资源。
- 自审修复后后端全量：`775 passed, 4 warnings in 356.71s`。四条均为既有弃用警告（Starlette anyio 别名、Alembic `path_separator` 两条、SQLite datetime）。
- Ruff 全量：`All checks passed!`（门禁别名 skip 识别补强后已复跑）。
- `git diff --check`：通过；文档纳入后再跑 P10/P11 阶段门：`15 passed, 2 warnings in 26.36s`。
- PR #123 首轮 CI 在 Ubuntu Python 3.11 暴露 `ast.dump` 跨版本差异；阶段门已改为统一换行后的完整函数源码 SHA，仍对删改负向断言 fail-closed。修复后 P10/P11 聚焦门：`19 passed, 2 warnings in 69.96s`；Ruff、mypy 均通过；后端全量：`775 passed, 4 warnings in 296.48s`。

上述测试均在默认离线 blocker 下运行，未读取真实 DSN 的值，未连接、探测、读写或清理任何真实外部资源。

## 保留 gap

- 无限不 EOF 或阻塞在 `next()`/cleanup 的 Runtime 仍无 deadline；未新增全局 Run deadline 或 adapter cancellation。
- 已开始的同步 Tool 无法由 Python future 强制终止；超时后只能关闭结果接纳并如实标记 `stop_state_unknown`，该 worker 可继续被占用。
- 未实现跨进程取消、Recovery 或 Task/Attempt。
- 真实验证 preflight 只是软件门；用户当次对目标、权限、数据边界和脱敏方式的授权仍是独立人工操作门。
