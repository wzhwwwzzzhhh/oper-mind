# P10 Harness Contract Kernel 与回归基线 · 实施 Design

> 状态：P10 已立项，Workpack 计划已由用户确认；结构性独立 Review PASS，Safe Trace 已通过目标 Python 3.11.9 与 GitHub CI 回归；立项与计划文档合入 `main`、建立干净实施 base 且开始门禁通过前不进入代码实施
> 更新：2026-09-01
> Issue：[#113](https://github.com/wzhwwwzzzhhh/oper-mind/issues/113)
> PRD：[P9-harness-contract-kernel.md](../../prd/agent-runtime/P9-harness-contract-kernel.md)
> 上游研究：[P9AgentHarness正式化Design.md](P9AgentHarness正式化Design.md)、[P9AgentHarness综合设计矩阵.md](P9AgentHarness综合设计矩阵.md)、[P9AgentHarness最终取舍与后续建议.md](P9AgentHarness最终取舍与后续建议.md)

## 1. 本 Design 的决策范围

本文是 P9 规划产出并已独立立项为 P10 的实施 Design，只为已确认 PRD 的三个切片确定可实施结构：

1. **Harness Contract Kernel**：七类正交状态命名空间与通用 identity / version / generation / fencing value objects；
2. **Adapter Contract Test Harness**：框架无关的 reference Adapter contract suite，以及当前 `DiagnosisExecutor` / `ToolGateway` 的兼容性 profile；
3. **Regression Baseline**：固定现有 Run、Tool、安全 Trace、取消和固定动作链的确定性行为，并用机器门禁证明零行为变化。

本 Design 不实现 P9 建议分期 A 的其余内容，也不进入 B–E。不新增 Task / Attempt / ContextManifest / BindingSnapshot，不接入 Registry、Policy、UoW、Event Pipeline、Recovery、Grant、durable worker 或长期记忆。

本 Design 的技术边界已经确认，用户又于 2026-09-01 将本候选独立立项为 P10 并确认 Workpack 计划。立项与计划文档先合入 `main`，再从新的干净 base 创建实施 worktree；开始门禁通过后按 Workpack、Review 和 evidence 门推进。

## 2. 当前代码基线与诚实缺口

### 2.1 Runtime 主链

当前正式链路是：

```text
RunApplicationService
  → DiagnosisExecutor.stream(query, service_id)
    → CoordinatorDiagnosisExecutor
      → CoordinatorAgent.route_stream(query)
  → DiagnosisExecutionEvent / DiagnosisExecutionResult
  → Run CAS + Result / Message / RunEvent 持久化
```

现有 `backend/src/application/contracts.py` 已定义 `DiagnosisExecutor` Protocol、结构化安全事件、结构化完成结果和安全 `DiagnosisExecutionError`。它是当前正式应用 port，不应被删除、改签名或静默替换。

当前 port 的能力与缺口：

| 项目 | 当前事实 | 本包处理 |
|---|---|---|
| 流式事件 | 支持 Iterator 事件 + 最终结果 | 作为 supported baseline |
| 服务上下文 | `service_id` 可传入；兼容旧测试端口的反射 fallback 仍存在 | 作为 mapped capability，不改 fallback |
| 安全事件/结果 | 已有 Pydantic 契约；`tool_invoked.summary` 已改为只由受控 status 生成的固定中性摘要，并在 Adapter / Application 双边界投影 | 作为 AC9 前置已修保证纳入 baseline；P10 不再改生产行为 |
| typed failure | 显式 error item 通过 `DiagnosisExecutionError` 表达；factory、route、collector 等意外异常仍可逸出 | 显式 error 作为 mapped；意外异常归一化作为 expected gap |
| capability 声明 | 无 | 只在测试 profile 中声明，不接生产 DI |
| absolute deadline | port 无输入 | expected gap，不补实现 |
| adapter-level cancellation | port 无取消信号；Run service 只在事件之间轮询持久化 cancel 状态 | `externalized` gap，不改生产链 |
| checkpoint / resume | 无 | 不属于本包，不增加能力 |

### 2.2 ToolGateway

`backend/src/core/tool_gateway.py` 是当前模型调用 Tool 的唯一受控入口，已覆盖显式注册、JSON / schema 最小校验、限时等待、脱敏、安全异常和结构化调用记录。它不是 Runtime Adapter，也不会实现 Runtime Adapter Protocol。

当前必须如实保留的边界：

- “allow”只表示 Tool 已显式注册且参数通过现有校验，不表示已经存在通用 Policy / Grant；
- timeout 表示调用方等待超时，不证明底层同步 Tool 已停止；不得把它升级为副作用安全保证；
- Gateway record 是本次调用的安全记录，不等于已经存在持久化 ToolCall / Result 领域对象；
- Approval、Grant、unknown outcome、Recovery 均不在本包补齐。

### 2.3 Run、取消、Trace 与固定动作

当前 Run 只有 `queued/running/succeeded/failed/cancelled` 五态。取消由数据库 CAS 写入 `cancelled`，执行循环在事件间检查；`_complete_success` / `_complete_failure` 对已有终态做保护，但无法中断正在阻塞的 Runtime 或 Tool。

当前固定动作已有 Proposal、人工决定、执行、Verify 和审计事件，但尚未具备 P9 目标中的 ExecutionGrant、unknown-outcome reconciliation 或 durable recovery。本包只建立现有行为回归，不把当前固定动作描述成目标 Harness 已完成。

### 2.4 Safe Trace 前置阻塞（工作区已修复并验证）

独立 Review 曾确认：`CoordinatorDiagnosisExecutor._event_data()` 会把 `tool_invoked.detail[:280]` 直接放入 `summary`，`RunApplicationService._safe_event_data()` 只校验其类型和长度后原样持久化。正常图路径通常从已做基础脱敏的 `ToolGateway` record 取 detail，但公开 Adapter 边界自身仍可接受任意 Coordinator / Executor 事件，因此当时不能证明 AC9。

该问题不是 expected gap，也不得被 zero-behavior baseline 固化。用户已授权在前置收口中顺手修复；当前工作区已完成：

1. `application/contracts.py` 以封闭 status allowlist 生成固定中性摘要，不接受自由文本作为摘要来源；
2. `CoordinatorDiagnosisExecutor` 忽略 `tool_invoked.detail`，只投影受控 status、有限 duration、role 与 service；
3. `RunApplicationService` 在持久化前再次丢弃 Executor 自由文本并重建摘要，假执行器也不能绕过；
4. 负向样例覆盖原始 SQL、Windows/POSIX 路径、凭据、原始异常、Prompt 和原始 Tool 输出，并覆盖最终 RunEvent 持久化；
5. 在 PR #114 合并前的目标 Python 3.11.9 最新主线复验中，聚焦回归 `38 passed`、后端全量 `647 passed`、mypy 与 ruff 通过；GitHub 后端、前端与 Gitleaks CI 全部通过。

该修复属于 `docs/prd/session/structured-diagnosis-result-truthfulness.md` AC7 的既有前置收口，不扩入 P10 实施范围。由于仓库根 `.venv` 的基础解释器已被卸载，验证使用隔离的便携 Python 3.11.9 与仓库锁定依赖完成；临时环境验证后已清理，未修改系统 Python 或仓库 `.venv`。修复与规划文档已经 PR #114 Review、CI 并合入 `main`，作为 P10 clean base 的既有证据。

## 3. 模块放置与依赖方向

### 3.1 新增模块

未来 Workpack 只允许新增以下生产树契约文件；它们在本包内不得被任何现有生产入口导入：

```text
backend/src/domain/harness_contracts.py
backend/src/application/runtime_contracts.py
```

依赖方向固定为：

```text
src.application.runtime_contracts
  ├── src.domain.harness_contracts
  └── src.application.contracts

tests/support/harness_contracts
  ├── 上述两个新契约模块
  ├── 当前 DiagnosisExecutor
  └── 当前 ToolGateway
```

- `domain/harness_contracts.py` 只依赖标准库与既有 Pydantic；不依赖 application、core、agents、infrastructure 或 api。
- `application/runtime_contracts.py` 可复用当前 `DiagnosisExecutionEvent`、`DiagnosisExecutionResult` 与 `DiagnosisExecutionError`，避免创建第二套安全 DTO；不依赖 core、agents、infrastructure 或 api。
- 不修改 `application/contracts.py`，不修改任何 `__init__.py` 导出，不在 `api/v1/dependencies.py`、`app.py` 或 Runtime 实现中注册新 contract。
- 现有生产模块反向导入新模块即视为越界，机器门禁必须失败。

### 3.2 为什么不放进 `core/` 或 `agents/`

`core/` 当前承载具体 Coordinator、图、LLM、Debate 与 Reflection 实现，`agents/` 承载领域 Agent。Harness 语义类型不应依赖具体图或 Agent；Runtime port 属 application 边界，通用值对象属 domain 边界，因此不新增顶层 `harness/` 分层，也不把契约塞入 LangGraph 实现目录。

### 3.3 与现有 `DiagnosisExecutor` 的关系

本包不创建第二个已激活生产 port。`RuntimeAdapterContract` 是未接线的目标契约，用于 reference Adapter 和兼容性测试；当前 `DiagnosisExecutor` 继续是唯一生产执行 port。

后续若需要激活新 Adapter，必须另行 Design 决定复用、演进或替换关系。本包只提供以下可验证映射，不修改任一生产调用点。

## 4. Contract Kernel 结构

### 4.1 共同模型规则

所有跨层 contract model 使用 Pydantic，统一：

```text
extra = forbid
frozen = true
显式 contract_version
UTC aware datetime
无隐式 dict 协议
```

不新增依赖；使用当前 requirements 已锁定的 Pydantic。公开类与函数有完整类型标注和中文 docstring。

### 4.2 通用 value objects

`domain/harness_contracts.py` 只定义机械语义，不定义业务对象：

| 类型 | 字段与校验 | 明确不证明 |
|---|---|---|
| `HarnessIdentity` | `namespace` + UUID；namespace 使用有限字符和长度 | 不证明 Run/Task/Attempt 类型、所有权或授权 |
| `ContractVersion` | 非负 `major/minor`；本包只接受精确版本匹配 | 不做自动协商、升级或降级 |
| `Generation` | 非负整数、可排序 | 不等于 lifecycle version 或重试次数 |
| `FencingToken` | opaque UUID，只允许相等比较和稳定序列化 | 不构成权限、Grant 或外部副作用证明 |

本包不定义 `TaskId`、`AttemptId`、`ToolCallId`，也不把这些值写入数据库。

### 4.3 七类正交维度

七个维度使用不同的 tagged Pydantic value model，序列化时保留固定 `dimension` tag；所有 code 都来自 v1 封闭枚举或封闭的完整 ID 集合，不接受 fixture 注入的自由字符串，防止同名 code 跨维度被 Pydantic 静默接受：

| 维度 | 目标类型 | 本包闭合范围 |
|---|---|---|
| lifecycle | `LifecycleStateValue` + `LifecycleStateCode` | `created/ready/running/waiting/completed/failed/cancelling/cancelled` |
| result | `ResultDispositionValue` + `ResultDispositionCode` | `complete_result/partial_result/no_result/pending` |
| external outcome | `ExternalOutcomeValue` + `ExternalOutcomeCode` | `not_executed/executed_unverified/succeeded/failed/outcome_unknown` |
| failure | `FailureCodeValue` + `FailureCodeId` + `FailureNamespace` | 完整 ID 封闭为 `validation.invalid_request/runtime.unexpected_exception/runtime.unsupported_capability/model.execution_failed/tool.rejected/tool.timeout/policy.denied/approval.required/budget.exceeded/cancel.requested/recovery.required/persistence.conflict/internal.invariant_violation`；namespace 从 ID 派生并校验一致 |
| resolution | `ResolutionDispositionValue` + `ResolutionDispositionCode` | `automatic/manual_required` |
| dispatch overlay | `DispatchOverlayValue` + `DispatchOverlayCode` | `idle/lease_acquired/dispatch_recorded/worker_started/released/lease_expired/reassigning` |
| control overlay | `ControlOverlayValue` + `ControlOverlayCode` | `normal/blocked_for_repair`；不实现 RepairCoordinator |

这些枚举只是 contract v1 的最小词汇，不规定允许的迁移、不绑定 Run/Task/Attempt/ToolCall 所有权、不产生事件或持久化，也不声称穷尽未来对象词汇。未来扩词必须提升 contract version 并重新进入 Design；fixture 只能选择上述值，不能扩展集合。这样既满足“typed、封闭、跨维度拒绝”，也不会偷渡 Task/Attempt 状态机。

## 5. Runtime Adapter Contract 与 capability profile

### 5.1 目标 Protocol

`application/runtime_contracts.py` 计划定义：

- `RuntimeExecutionRequest`：`execution_id`、contract version、query、可选 `service_id`、绝对 `deadline_at`；这里只承载当前可映射的请求上下文，不是 ContextManifest。
- `RuntimeControl` Protocol：只读 `is_cancel_requested()` 与 `remaining_seconds()`；reference Adapter 用它验证取消和 deadline，当前生产 port 不接入。
- `RuntimeCapability` 与 `RuntimeCapabilityProfile`：版本化声明支持、mapped、externalized 或 unsupported；声明不是授权。
- `RuntimeEventSignal`：`kind: Literal["event"]` + 当前 `DiagnosisExecutionEvent` wrapper。
- `RuntimeResultSignal`：`kind: Literal["result"]` + 当前 `DiagnosisExecutionResult` wrapper；明确只是当前 Run 兼容结果，不是未来 Task ResultAcceptance。
- `RuntimeFailureSignal`：`kind: Literal["failure"]` + 稳定 `FailureCodeValue` + 安全 message，不保存原始异常。
- `RuntimeSignal`：以 `kind` 为 discriminator 的 `Annotated` union；不要求既有 DTO 自带 discriminator。
- `RuntimeAdapterContract` Protocol：`capabilities()` + `stream(request, control)`；只供 reference / test compatibility 使用，不进入生产 DI。

目标 reference Adapter 的 stream 规则固定为：零到多个 event 后，恰好一个 result 或 failure 终止；禁止零终止信号、多个终止信号以及终止后继续发 event。reference suite 必须逐项打破这些规则并验证失败类别。

### 5.2 当前 `DiagnosisExecutor` 映射

| 目标 contract | 当前来源 | profile 状态 | 断言 |
|---|---|---|---|
| query | `stream(query, ...)` | supported | 原值传递 |
| service context | 可选 `service_id` 参数 | mapped | 新签名执行器收到 service；旧单参数 fake 仍由现有 fallback 兼容 |
| execution_id | Run service 持有，executor 签名无该字段 | externalized | probe 证明不会传入当前 port；不伪造映射 |
| contract_version | 当前 port 无版本输入 | mapped | compatibility wrapper 精确校验后才调用当前 port；不宣称当前 port 原生支持版本 |
| control | Run service 外层轮询取消；executor 无 control | externalized | wrapper 不宣称可中断当前 executor |
| stream event shape | `DiagnosisExecutionEvent` | supported | typed 与字段白名单；内容安全须先满足 §2.4，不在 profile 中提前报 supported |
| final result | `DiagnosisExecutionResult` | mapped | 只映射当前兼容结果，不宣称 Task accepted |
| 显式 typed failure | `DiagnosisExecutionError` | mapped | 转 `RuntimeFailureSignal`，不暴露 traceback / 原始异常 |
| unexpected exception | factory / route / collector 异常可逸出当前 port | unsupported | expected gap；reference Adapter 必须归一化，当前 port 不改行为 |
| terminal cardinality | 当前 port 不强制恰好一个 result/error，也不禁止终止后事件 | unsupported | expected gap；只验证代表性当前流，不把它冒充强保证 |
| capability declaration | 无生产接口 | externalized | reviewed profile / compatibility probe 持有，不改 executor，也不宣称当前 port 自带声明 |
| deadline | 无 | unsupported | expected gap 精确断言 |
| adapter cancellation | Run service 外层轮询 | externalized | 不宣称 Runtime 可中断；expected gap 精确断言 |

### 5.3 两层 contract suite

1. **Reference conformance**：确定性 fake Adapter 对正常结果、typed failure、不支持能力、deadline、取消、完整 request 字段传递、service context 和 stream cardinality 全部通过；测试本身不得连接模型或外部资源。
2. **Current compatibility**：`DiagnosisExecutorCompatibilityProbe` 只存在于 `backend/tests/support/`，以实际调用和失败注入计算 observed capability；supported / mapped 子集必须通过，unsupported / externalized 必须被行为探针证实为 expected gap。

reviewed expected profile 使用只增不改的版本化 JSON fixture；本包首次创建：

```text
backend/tests/fixtures/harness/current_capability_profile.v1.json
```

fixture schema 固定包含 `contract_version`、`profile_version` 和完整 capability map；每项必须有 `expected_status`、可空 `gap_id`、`evidence.kind`、`evidence.locator` 与 `evidence.assertion`。probe 不读取 expected fixture，也不得直接返回 fixture 中的 status；它只返回由执行结果推导的 observed facts。comparator 对 capability key 集合、status、gap ID 和证据 locator 做精确比较。

版本棘轮使用 baseline base commit 中的 fixture 历史做机器比较：已存在的 `current_capability_profile.vN.json` 必须 byte-for-byte 不变；能力或 gap 变化只能新增连续的 `vN+1` 文件，且 payload `profile_version` 必须等于文件名版本。latest fixture 才参与 observed 比较，旧版本保留为审计历史。本包 base 中没有该 fixture 时只允许创建 `v1`；若 base 已有历史却覆盖旧文件、跳号或内容变化但未新增版本，门禁失败。

新增未知 gap、已声明支持却失败、expected gap 证据失效或 gap 变化但 profile version 未提升都使测试失败。expected fixture 与 probe 同时修改仍需 Review 在 Workpack evidence 中逐项解释；机器门禁负责拒绝遗漏与不一致，不能替代 Review。不得使用 `skip`、`xfail` 或放宽断言表达 gap。

## 6. ToolGateway 与现状回归基线

### 6.1 ToolGateway 单独验证

ToolGateway 不实现 Runtime Adapter contract。测试复用当前公开行为，并把以下事实写入同一 versioned capability fixture：

| 场景 | 当前 oracle | 禁止误读 |
|---|---|---|
| 未注册 Tool | rejected，Tool 不执行 | 不等于通用 Policy deny |
| 非法 JSON / 非对象 / 缺参数 / 类型错误 | rejected | 不宣称完整 JSON Schema 支持 |
| 成功 | 返回脱敏 output + 完整安全 record | 不等于持久化 ToolResult |
| 敏感输出 | 命中规则后脱敏 | 不替代上游数据分类 |
| timeout | 返回 timeout 安全结果 | 不证明底层线程或副作用停止 |
| Tool 异常 | 中性 error，不泄露异常 | 不做 Recovery / Retry |

### 6.2 Regression Baseline 测试矩阵

| 保护面 | 复用现有测试 | 本包新增断言 |
|---|---|---|
| Run 受理/终态 | `test_p2_application_services.py` | 终态不被迟到 success/failure 覆盖；不新增状态 |
| Runtime 安全适配 | `test_p2_diagnosis_adapter.py`、`test_p43_service_context.py` | capability profile 与映射一致 |
| ToolGateway | `test_tool_gateway.py`、`test_agent_gateway.py` | expected gap 与敏感负向输入门禁 |
| Safe Trace | `test_p2_diagnosis_adapter.py`、`test_p2b_tool_trace.py`、`test_p2_application_services.py`、`test_log_event_service_id.py` + API 相关场景 | 复跑已落地的自由文本负向样例；公开 Adapter 与持久化 RunEvent 只能出现 status 派生的固定摘要，否则 P10 实施不得启动 |
| 取消 | `test_run_cancel.py` | queued 不启动、running 后续事件停止、迟到完成不覆盖 cancelled；明确无法中断阻塞执行 |
| 固定动作 | `test_p5_controlled_action.py` 及 action repository/API 既有测试 | 使用 fake executor 的 Proposal → approve → request → execute → Verify 确定性闭环；状态、事件、幂等和生产目标拦截保持现状 |

新增回归测试不得连接真实 PostgreSQL、模型、主机、日志系统或网络。固定动作闭环使用临时 SQLite 应用库和确定性 `ControlledActionExecutor` fake；不调用真实目标执行器。

### 6.3 Snapshot 纪律

- 只快照 typed 字段和稳定枚举；运行 ID、UUID、绝对时间和耗时先归一化。
- 不快照整段模型报告、原始 Tool 输出、异常或 LangGraph 私有 state。
- “当前保证”“当前 expected gap”“未来目标”分栏记录，gap 不能被描述成已交付能力。
- 负向输入被 validator / gate 拒绝，承载断言的 pytest 用例本身通过；仓库不提交故意失败测试。

Safe Trace 不使用“正常 ToolGateway 上游已经脱敏”的窄样例替代公开边界负向测试；§2.4 的已落地恶意输入与持久化测试必须在 P10 实施 base 上继续通过。

## 7. 零行为变化机器门禁

### 7.1 基线捕获

P10 Workpack 计划已经用户确认。立项与计划文档合入 `main` 后，必须在干净实现 worktree 中，从已记录且已确认、已合并的确定 base commit 生成 baseline；不得在其他功能分支或已经包含 P10 业务代码的工作区捕获：

```text
backend/tests/fixtures/harness/zero_behavior_baseline.v1.json
```

基线至少记录：

- base commit SHA；
- 规范化 `app.openapi()` JSON 的 SHA-256；
- Alembic head 集合；
- `backend/requirements.txt`、`backend/pyproject.toml`、`frontend/package.json`、`frontend/package-lock.json` 的 Git-canonical SHA-256；
- 以 base commit 的 `git ls-tree -r --name-only <base>` 为唯一输入清单，对其中 `backend/migrations/**`、`backend/src/api/v1/**`、`frontend/**` 的 tracked Git blob 做聚合 SHA-256；当前缺失或内容变化失败；
- `backend/src/app.py`、`backend/src/application/contracts.py`、`backend/src/application/services.py`、`backend/src/application/action_services.py`、`backend/src/core/tool_gateway.py`、`backend/src/infrastructure/diagnosis/coordinator_executor.py`、`backend/src/api/v1/dependencies.py` 的 Git-canonical SHA-256；
- contract module 允许路径和文档 / 测试允许路径；
- generator 文件自身的 reviewed raw SHA-256、跨平台 canonical SHA-256 与生成时 bootstrap dirty-path inventory；
- 基线 skip / xfail inventory：通过 AST 记录 pytest / unittest 的跳过与预期失败入口之文件、所属测试、类别和条件摘要。

所有 tracked 内容哈希都禁止直接对 checkout `read_bytes()`：baseline 通过 Git plumbing 读取 `<base>:<path>` 的 blob 原始 bytes 并计算 SHA-256；持续校验读取当前 `HEAD:<path>` 的 blob bytes。聚合哈希按 POSIX path 排序，对每项使用 `UTF-8 path + NUL + blob SHA-256` 的稳定 framing 后再求 SHA-256。这样 CRLF checkout、`core.autocrlf` 和不同 OS 不改变结果；working tree / index 的任何漂移由四集合 diff 负责，不靠 checkout raw hash 猜测。

生成器只使用 Python 标准库和现有应用依赖，放在 `backend/tests/support/harness_zero_behavior.py`。它是 Workpack 的第一个代码 bootstrap，不再错误要求“生成器尚不存在时工作区零变更”。默认模式只校验；显式写模式必须同时提供 `--write-baseline --base-sha <sha> --reviewed-generator-raw-sha256 <reviewed-sha>`，并满足：

1. `HEAD` 等于指定 base；
2. 当前 worktree 的实际 generator raw SHA-256 与 Reviewer 通过 `Get-FileHash` 得到并传入的 `reviewed-sha` 完全相同；同时把 generator 解码为无 BOM UTF-8、将 CRLF / CR 规范化为 LF 后计算 canonical SHA-256 并写入 baseline；
3. committed / staged / unstaged / untracked 四集合并集只能是以下 bootstrap 集合的子集：`backend/tests/support/harness_zero_behavior.py`、`docs/workpack/harness-contract-kernel/plan.md`、`docs/workpack/README.md`；其中 generator 必须存在，两个管理文档可以已经在 base 中或处于待提交状态；
4. 任何生产代码、测试、fixture、依赖、API、迁移或前端变化都使写模式拒绝运行。

检查通过后，`zero_behavior_baseline.v1.json` 才作为第二个代码工件生成。该流程允许经过 Review 的单一生成器启动，同时不允许其他候选代码先于现状取样。

bootstrap generator 必须在首次 Review 时已经同时具备 write 与 verify 全部逻辑；baseline 记录 hash 后保持不变。若之后发现 generator 缺陷，必须删除 baseline 及其后新增的候选测试/fixture/contract，回到同一 clean base 的 bootstrap 步骤，以新 reviewed hash 重新生成；禁止保留后续代码同时刷新 baseline。

后续 worktree / CI 复验 generator 使用 canonical SHA-256；同一 bootstrap worktree 的写入授权使用 reviewed raw SHA-256，防止 Review 后文件变化。generator 最终进入 Git 后，其 LF Git blob bytes 必须与上述 UTF-8/LF canonical bytes 一致，否则门禁失败。

聚合哈希明确不遍历工作目录“全部现存文件”：Git ignored 的 `node_modules`、`dist`、`__pycache__`、`.pyc`、coverage/cache/build 等环境产物一律不进入 baseline。非 ignored untracked 文件由四集合门禁直接拒绝；新增 tracked 文件由 committed/staged diff 和 allowlist 判定。

### 7.2 持续校验

`backend/tests/test_harness_zero_behavior_gate.py` 必须机器验证：

1. 依赖文件、迁移目录、API、前端和关键生产文件哈希与基线一致；
2. 当前规范化 OpenAPI 哈希与 Alembic heads 与基线一致；
3. 分别收集 committed（`git diff --name-only <base>...HEAD`）、staged（`git diff --cached --name-only`）、unstaged（`git diff --name-only`）和 untracked（`git ls-files --others --exclude-standard`），对四者规范化、去重后的全集执行精确 allowlist；任何集合都不能省略；
4. 通过 AST 扫描确认：除 `src.application.runtime_contracts` 外，`backend/src` 既有生产模块不导入 `src.domain.harness_contracts`；任何生产模块都不导入 `src.application.runtime_contracts`；
5. 新 contract module 不导入 core、agents、tools、infrastructure、api 或具体 Agent 框架；
6. 当前 `DiagnosisExecutor`、`CoordinatorDiagnosisExecutor`、`RunApplicationService`、`ToolGateway` 与生产 DI 文件没有 diff；受保护目录新增 staged / unstaged / untracked 文件同样失败；
7. 当前 skip / xfail AST inventory 与 baseline 完全一致，且所有 `test_harness_*` 与 Harness support 文件中 inventory 为空；扫描至少覆盖 `pytest.skip/xfail/importorskip`、`pytest.mark.skip/skipif/xfail`、`pytest.param(..., marks=...)`、模块级 `pytestmark`、`unittest.skip/skipIf/skipUnless/expectedFailure`，并解析常见模块别名与 `from ... import ... as ...`；不以 pytest 退出码代替该棘轮；
8. base 中已存在的 `current_capability_profile.vN.json` 保持 byte-for-byte 不变，新版本连续递增且 payload 版本与文件名一致。

只写“人工看过 diff”不能通过。若基线因 main 上其他已合并改动失效，必须先 rebase，在无候选代码改动的状态重新生成基线并经 Review；不得在同一提交里一边改受保护文件一边刷新基线。

### 7.3 允许路径

实施 Workpack 默认只允许：

```text
backend/src/domain/harness_contracts.py
backend/src/application/runtime_contracts.py
backend/tests/support/__init__.py
backend/tests/support/harness_contracts.py
backend/tests/support/harness_zero_behavior.py
backend/tests/fixtures/harness/current_capability_profile.v1.json
backend/tests/fixtures/harness/zero_behavior_baseline.v1.json
backend/tests/test_harness_contract_kernel.py
backend/tests/test_harness_runtime_adapter_contract.py
backend/tests/test_harness_regression_baseline.py
backend/tests/test_harness_zero_behavior_gate.py
docs/workpack/P10-harness-contract-kernel/**
docs/workpack/归档/P10-harness-contract-kernel/**
docs/workpack/README.md
docs/design/agent-runtime/P9HarnessContractKernel实施Design.md
docs/prd/agent-runtime/P9-harness-contract-kernel.md
docs/prd/agent-runtime/README.md
docs/prd/README.md
```

`backend/tests/support/__init__.py` 只在干净 worktree 确认该目录必须作为普通 package 且文件尚不存在时允许新增；若无需新增，保持无 diff。allowlist 是上限，不是必须改动清单，也不允许以 `docs/**` 或“相关索引”等模糊规则扩张。

Workpack 完成交付时允许把同名目录从 active 位置移动到上述精确归档位置，并同步 `docs/workpack/README.md`；不得借归档开放其他 Workpack 或宽泛 `docs/workpack/归档/**`。

实现 Design 经确认后若需增加路径，必须先 Review 是否仍属三个切片；命中任何 PRD 排除项则停止并另行决策，不能扩 allowlist 绕过门禁。

## 8. 实施切片与文件面

### 8.1 P10 Workpack 前置步骤

P10 已由用户独立立项且 Workpack 计划已确认，本节现作为计划确认与代码实施之间的强制前置门；立项与计划文档合入 `main`、建立干净实施 base 前仍不执行以下代码步骤。

1. 确认 §2.4 Safe Trace 修复已纳入前置收口、在正式 Python 3.11 环境复跑并形成已合并证据；没有 clean-base 证据则停止；
2. 从已确认、已合并的 base 创建干净分支或 worktree；在创建 active Workpack 文档和任何代码前，`git status --porcelain=v1 --untracked-files=all` 必须为空并记录 `$baseSha = git rev-parse HEAD`；
3. 按已确认 Design 创建 active Workpack 并获得用户计划确认；其 plan / README 是 §7.1 唯一允许的非代码 bootstrap 差异；
4. 确认根 `.venv` 可执行；若新 worktree 无可用环境，按仓库 Windows 规则重建，不改 requirements / pyproject 或任何锁定依赖；
5. 先运行现有聚焦回归与后端全量测试；基线不绿则不进入开发；
6. 只新增 `harness_zero_behavior.py`，经 Review 计算 SHA-256 后以显式写模式生成 baseline；baseline 生成成功前不得新增其他测试、fixture 或 contract module。

Windows 环境检查与重建命令固定为：

```powershell
python --version
python -m venv .venv
$env:PYTHONUTF8=1
$env:PYTHONIOENCODING="utf-8"
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe --version
```

若 `python --version` 不能提供项目支持的 Python 版本，先停止并由环境层提供解释器；不得修改项目依赖来迁就坏环境。当前已失效的 `.venv` 不复制到新 worktree，也不作为任何 evidence。

generator bootstrap 从仓库根执行，`reviewed-sha` 必须来自 Review 后的同一文件：

```powershell
$baseSha = git rev-parse HEAD
Get-FileHash backend/tests/support/harness_zero_behavior.py -Algorithm SHA256
$reviewedGeneratorSha = "<Workpack-evidence-中已复核的-sha256>"
.\.venv\Scripts\python.exe backend/tests/support/harness_zero_behavior.py --write-baseline --base-sha $baseSha --reviewed-generator-raw-sha256 $reviewedGeneratorSha
```

命令参数不构成自我批准：Workpack evidence 必须记录 Reviewer 核对的 generator diff 与 hash；文件在核对后变化会因实际 hash 与传入值/记录值不一致而失败。

### 8.2 三个切片

| 切片 | 允许改动 | 完成证明 |
|---|---|---|
| 1. Contract Kernel | 新增 `domain/harness_contracts.py` 与对应测试 | 七维 tag 防串用；value object round-trip/非法值/比较测试全过 |
| 2. Adapter Contract Harness | 新增 `application/runtime_contracts.py`、test support、capability fixture 与 Adapter tests | reference 100% conformance；current profile 无未知 gap；生产 import graph 不变 |
| 3. Regression + Boundary Gate | 新增回归测试、zero-behavior support/fixture/gate 与 evidence | Run/Tool/Trace/cancel/action 基线全绿；四集合 diff、受保护路径、skip/xfail 棘轮全绿；后端全量测试通过 |

三个切片放在同一 Workpack，按顺序实现；任何切片触发已有生产文件修改即暂停，而不是顺手修复。

## 9. 验证命令与 AC 映射

### 9.1 具名证明矩阵

以下均为未来 Workpack 必须新增或复用的测试 oracle；名称可按 pytest 编码约束机械调整，但语义、输入和失败条件不可删减：

| AC | 测试 / fixture | 核心 oracle 与失败条件 |
|---|---|---|
| AC1 | `test_harness_contract_kernel.py::test_七维同名code不能跨维度解析` | 七个 model 分别 round-trip；任一 model 接受另一 dimension tag、自由 code 或错误 Failure namespace 即失败 |
| AC2 | 同文件 `test_identity_version_generation_fencing合法往返并拒绝非法值` | 固定序列化；空 namespace、非法 UUID、负版本/代数、禁止排序 fencing 均拒绝 |
| AC3 | 同文件 `test_kernel不包含阶段B业务实体或持久化映射` + import AST gate | 出现 Task/Attempt/Context/Binding 类型、ORM 或受禁依赖即失败 |
| AC4 | `test_harness_runtime_adapter_contract.py` 的 reference 参数化套件 | query、execution_id、version、service、deadline、control 全字段可观察；0..n event + 恰一 terminal；零/多 terminal、terminal 后 event、意外异常未转 typed failure 均失败 |
| AC5 / AC15 | `current_capability_profile.v1.json` + `test_current_diagnosis_executor_observed_profile精确匹配reviewed_expected` | observed probe 独立执行；capability key/status/gap ID/evidence/version 任一未知或不一致即失败 |
| AC6 / AC11 | `test_harness_regression_baseline.py::test_toolgateway拒绝非法请求且拒绝时不执行tool` | 未注册、坏 JSON、非对象、schema 错误、异常、敏感 output；拒绝计数必须为零次执行且安全结果无原始值 |
| AC7 | 同文件 `test_run代表性生命周期和迟到终态保持现状` | 只接受当前五态；迟到 success/failure 不覆盖终态；不读取 graph 私有 state |
| AC8 | 同文件 `test_cancel保持协作式检查点和终态保护` | queued 不启动、running 在下一事件停止、迟到完成不覆盖 cancelled；阻塞调用不可中断被固定为 limitation |
| AC9 / AC11 | 同文件 `test_tool_invoked公开投影拒绝敏感summary` | 直接向公开 Adapter 边界分别注入 SQL、Windows/POSIX 路径、credential、原始异常；API/持久化事件均不得出现原文；前置修复未满足则本测试失败并阻断候选实施 |
| AC10 | 同文件 `test_固定动作从提案到独立验证保持既有边界` | 临时 SQLite + fake executor 完整走 Proposal → approve → request → execute → Verify；逐步断言既有状态、审计事件、幂等、生产目标拦截，无 Grant 或新增权限 |
| AC12 | 同文件 `test_代表性场景归一化后重复运行一致` | 固定 clock/UUID/fake，连续两次结果相同；任何网络、真实模型、主机、日志或用户服务访问即失败 |
| AC13 | `test_harness_zero_behavior_gate.py::test_skip_xfail_inventory未增长且候选文件为零` | AST inventory 与 base 精确相等，候选文件为零；新增/扩大 skip、skipif、xfail、pytest.xfail 任一即失败 |
| AC14 | 同文件的 dependency / OpenAPI / Alembic / four-diff-set / import tests | 任一哈希变化、任一 committed/staged/unstaged/untracked 越界、生产导入或受保护路径新增文件即失败 |
| AC16 | `test_harness_zero_behavior_gate.py::test_正式路线图P10范围与PRD一致` | 路线图必须把三个切片立项为 P10 且不把 A–E 标成批准实施；只读校验，不由测试改文档 |

### 9.2 执行命令

后端命令均从 `backend/` 执行，并使用根 `.venv`：

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_harness_contract_kernel.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_runtime_adapter_contract.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_regression_baseline.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_harness_zero_behavior_gate.py -q
..\.venv\Scripts\python.exe -m pytest tests/test_p2_application_services.py tests/test_p2_diagnosis_adapter.py tests/test_p2b_tool_trace.py tests/test_tool_gateway.py tests/test_agent_gateway.py tests/test_run_cancel.py tests/test_p5_controlled_action.py tests/test_action_proposal_list.py tests/test_p43_service_context.py -q
..\.venv\Scripts\python.exe -m pytest tests -q
..\.venv\Scripts\python.exe -m ruff check src/domain/harness_contracts.py src/application/runtime_contracts.py tests/support/harness_contracts.py tests/support/harness_zero_behavior.py tests/test_harness_contract_kernel.py tests/test_harness_runtime_adapter_contract.py tests/test_harness_regression_baseline.py tests/test_harness_zero_behavior_gate.py
..\.venv\Scripts\python.exe -m mypy src/domain/harness_contracts.py src/application/runtime_contracts.py
```

仓库根执行：

```powershell
$baseSha = (Get-Content backend/tests/fixtures/harness/zero_behavior_baseline.v1.json -Encoding utf8 | ConvertFrom-Json).base_commit_sha
git diff --check
git diff --name-only "$baseSha...HEAD"
git diff --cached --name-only
git diff --name-only
git ls-files --others --exclude-standard
git status --porcelain=v1 --untracked-files=all
```

| PRD AC | 主要证明 |
|---|---|
| AC1–AC3 | Contract Kernel 类型、tag、round-trip、非法值和无业务实体测试 |
| AC4–AC5 | reference conformance + 独立 observed probe / reviewed expected profile 精确比较 |
| AC6 | ToolGateway 允许/拒绝/参数/异常/脱敏回归 |
| AC7–AC10 | Run、取消、Safe Trace、固定动作回归矩阵 |
| AC11–AC12 | 负向输入门禁、固定时钟/ID 与离线确定性重复运行 |
| AC13 | 新增套件、聚焦测试、后端全量测试、AST skip/xfail inventory 棘轮 |
| AC14 | zero-behavior baseline、四集合精确 allowlist、OpenAPI / migration / dependency / tool config / import graph gate |
| AC15 | versioned expected profile、独立 observed capability、gap evidence schema 与 Workpack evidence |
| AC16 | 已完成：正式路线图只把三个切片立项为 P10，不承诺完整 A–E |

前端未改且机器门禁要求 `frontend/**` 零 diff，因此本 Workpack 不运行前端测试来制造无关成本；若出现任何前端 diff，直接判定越界，而不是补跑前端命令后放行。

## 10. 风险、回滚与停止条件

| 风险 | 控制 |
|---|---|
| 新 contract 变成第二套生产 port | 不修改现有 port，不导出、不装配；AST import gate 阻止生产导入 |
| capability profile 掩盖回归 | expected gap 版本化、精确断言；未知 gap 与声明失真直接失败；禁用 xfail |
| 七维 vocabulary 被误当完整状态机 | v1 code 枚举封闭，但只定义 tagged value；不定义对象所有权、Task/Attempt 转移、writer 或持久化 |
| Tool timeout 被误称“已停止” | profile 固定记录 wait timeout，不声明副作用终止 |
| baseline 被随代码一起刷新 | 写基线必须在 base HEAD；保护文件变更与 baseline 刷新不得同提交 |
| staged / untracked 越界绕过门禁 | committed、staged、unstaged、untracked 四集合取并集；保护目录拒绝新增 untracked 文件 |
| 既有 skip 掩盖新增缺口 | AST inventory 以文件、所属测试、类别和条件摘要做等值棘轮；候选文件必须为零 |
| Safe Trace 泄漏被当成当前保证 | §2.4 修复及负向测试已落地；只有正式环境证据合并后才能作为 baseline 保证，失败样例不得被移除或放宽 |
| 回归 snapshot 过脆弱 | 只比较 typed 稳定字段，归一化 ID/时间，不快照模型正文和框架 state |
| 当前环境不可执行 | Workpack 前先修复本地虚拟环境并跑绿现有基线；环境修复不改锁定依赖 |

以下任一情况立即停止当前 Workpack 并回到 Design：

- 必须修改现有 `DiagnosisExecutor`、`CoordinatorDiagnosisExecutor`、`RunApplicationService`、`ToolGateway`、生产 DI 或 API 才能继续；
- 需要迁移、持久化新身份、公开 API、前端、依赖或真实外部资源；
- 需要 Task / Attempt / Context / Binding、Policy / Grant、Recovery 或 durable worker；
- 发现现有安全保证实际缺失且必须改行为才能修复；该问题应独立登记，不能让 baseline 把缺陷固化为保证。

最后一项曾由 `tool_invoked.summary` 内容安全缺口触发；该缺口已通过 PR #114 完成 fail-closed 修复与回归。若 P10 实施前又发现必须改变其他生产行为，继续在独立前置收口处理，不带入 P10 Workpack。

回滚方式是删除本包新增的未激活 contract / test / fixture 文件及对应 Workpack 状态回写；由于无生产 import、迁移、API 和数据变化，不需要数据回滚或运行时切换。

## 11. Review 与授权状态

当前已完成：

- P9 研究、最终取舍与 Reader Review；
- 正式路线图登记；
- PRD 用户确认；
- GitHub issue #113 创建。
- 本实施 Design 的结构性独立 Review：`PASS`；
- Safe Trace fail-closed 修复及恶意输入/持久化回归已通过 PR #114 合入 `main`；Python 3.11.9 聚焦 `38 passed`、全量 `647 passed`、mypy/ruff 与 GitHub CI 通过。
- 用户已于 2026-08-30 确认本实施 Design。
- 用户已于 2026-09-01 将本候选独立立项为 P10，并确认 Workpack 计划。

当前尚未完成：

- 立项与计划文档合入 `main`，并从新的干净 base 创建实施 worktree；
- 开始门禁、任何 P10 代码实现与交付证据。

首次独立 Review 的结论是 `NEEDS_REVISION`；经过三轮修订，最终结构性 Review 为 `PASS`，包括封闭类型、Adapter 映射、profile 棘轮、bootstrap、四集合 diff、跨 worktree hash 和具名 AC 证明。Review 发现的 Safe Trace 阻塞已修复，前置收口与 P9 规划文档已通过 PR #114 合入 `main`；目标 Python 3.11.9 聚焦 `38 passed`、全量 `647 passed`，GitHub 后端、前端与 Gitleaks CI 全部通过。P9 已完成规划收口，用户又于 2026-09-01 将本候选独立立项为 P10 并确认 Workpack 计划。当前下一工程门是先合入立项与计划文档，再建立干净实施 base；此前不开始代码。
