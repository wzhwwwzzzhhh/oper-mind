# P10 Harness Contract Kernel · 实施证据

> 日期：2026-09-01
> 当前范围：S1 Contract Kernel 已提交；S2 Adapter Contract Test Harness 已完成实现、验证与独立 Review（PASS，无 P0–P3）；S3 Regression Baseline 尚未开始
> 最终实施 base：`643c2c0c6d5630705ba89251a9cea58c505bb4ce`

## S1 · Contract Kernel

### 交付内容

- 新增 `backend/src/domain/harness_contracts.py`：
  - 七类带固定 `dimension` tag 的正交状态值；
  - v1 封闭 code / failure ID 集合与派生 failure namespace；
  - `HarnessIdentity`、`ContractVersion`、`Generation`、`FencingToken`；
  - `extra=forbid`、`frozen=true`、显式且精确匹配的 contract v1。
- 新增 `backend/tests/test_harness_contract_kernel.py`：
  - 七个维度分别执行合法 JSON round-trip，并与 Design 固定 tag 精确比较；
  - 七个维度分别拒绝错误 tag 与自由 code；同名 `failed` 在 Python enum 和序列化 payload 两个方向均拒绝跨维度解析；
  - identity/version/generation/fencing 非法值和比较边界；
  - 阶段 B 业务实体、ORM、框架私有依赖不存在的 AST 证明。

### AC 证据

| PRD AC | S1 证明 | 结果 |
|---|---|---|
| AC1 | 七个 tagged Pydantic value model 参数化验证固定 tag、round-trip、错误 tag 与自由 code 拒绝；`failed` 的 Python enum / 序列化 payload 双向跨维度输入均被拒绝；未新增万能 `status` 类型 | PASS |
| AC2 | identity、contract version、generation、fencing 合法往返；空/非法 namespace、非法 UUID、负版本/代数和 fencing 排序被拒绝 | PASS |
| AC3 | 源码与 AST 测试确认无 AgentTask、Attempt、ContextManifest、BindingSnapshot、ORM、状态机或持久化映射 | PASS |
| AC11（S1） | 跨维度 code、错误 namespace、额外 `status`、非 v1 版本等负向输入被分类拒绝，承载断言的测试本身通过 | PASS |
| AC12（S1） | 固定 UUID 与稳定 JSON round-trip，不访问网络、模型、数据库、主机、日志或用户服务 | PASS |
| AC13（S1） | 新增 S1 套件 `14 passed`，无 skip/xfail；后端全量 `661 passed` | PASS |
| AC14（S1） | 默认 zero-behavior 校验在实施前、实施后和全量回归后均 PASS；新模块无生产反向导入及受禁依赖 | PASS |

AC4–AC10、AC15 的完整证明属于后续 S2/S3，本轮未宣称完成。AC16 已由正式路线图完成。

### 验证记录

以下命令均在独立实施 worktree 执行；后端命令从 `backend/` 执行：

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_harness_contract_kernel.py -q
# 14 passed

..\.venv\Scripts\python.exe -m ruff check src/domain/harness_contracts.py tests/test_harness_contract_kernel.py
# All checks passed

..\.venv\Scripts\python.exe -m mypy src/domain/harness_contracts.py
# Success: no issues found in 1 source file

..\.venv\Scripts\python.exe -m pytest tests -q
# 661 passed, 2 warnings（既有依赖弃用警告）
```

仓库根执行：

```powershell
.\.venv\Scripts\python.exe backend/tests/support/harness_zero_behavior.py
# PASS: Harness 零行为基线校验通过

git diff --check
# PASS；仅出现既有文档 checkout 的 CRLF 提示
```

### 不变边界

- generator SHA-256 保持为 `0a7a05ed86e139d5528deeae64653e1fc478dba4fbc1ff4afa4429e01d9df5b8`。
- baseline SHA-256 为 `095b21121b58bc1ab2096fc268c6fc47ee1c0a7b1634f85f77850f915c732e65`。
- 本轮未修改 generator、baseline、依赖、迁移、API、前端、生产 DI、Runtime、Run service、ToolGateway 或其他既有生产文件。
- 接手时已有的开始门文档、generator 与 baseline dirty inventory 保持原样；S1 只新增契约模块、契约测试和本 evidence，并更新同一 Workpack 的 S1 勾选状态。

### 独立 Review 修订

- 首轮独立只读 Review 结论为 `NEEDS_REVISION`，发现 1 项 P2：AC1 的错误 tag / 自由 code 负向证明未逐一覆盖七个维度。
- S1 实施与 Review 收口涉及契约测试、本 evidence 和 plan 的状态/验证计数回写；其中 P2 代码修订只增加七维参数化负向门禁，以及 lifecycle / external outcome 的同名 `failed` enum 与 payload 双向拒绝。
- 修订后聚焦、ruff、mypy、zero-behavior 与后端全量验证均通过；独立复核确认 P2 已关闭、无 P0/P1/P2，并指出 1 项 P3 文档计数/范围一致性问题；本次已同步修正 plan 与 evidence，未修改 Contract Kernel、generator、baseline 或既有生产文件。

## 后续状态

- S1：完成并验证。
- S2：完成实现、验证与独立 Review（PASS，无 P0–P3）。
- S3：未开始。
- S1 重建后提交为 `1b91808`；S2 由本次提交收口；未推送、未创建 PR。

## S2 · Adapter Contract Test Harness

### 交付内容

- 新增 `backend/src/application/runtime_contracts.py`：
  - `RuntimeExecutionRequest`、`RuntimeControl` 与未激活的 `RuntimeAdapterContract`；
  - 完整 `RuntimeCapability` / status / versioned profile；
  - 以 `kind` 为 discriminator 的 event/result/failure signal；
  - 复用既有 `DiagnosisExecutionEvent` / `DiagnosisExecutionResult`，不创建第二套安全 DTO。
- 新增 `backend/tests/support/harness_contracts.py`：
  - reference Adapter、stream cardinality oracle 与 typed failure message 安全 oracle；
  - 仅用于测试的当前 `DiagnosisExecutor` compatibility wrapper；
  - 由真实 `CoordinatorDiagnosisExecutor` + 确定性 fake coordinator 事件计算 observed facts 的独立 probe；
  - 由真实 `ToolGateway` 调用计算 Design §6.1 六项 observed facts 的独立 probe；
  - reviewed/observed capability profile 封闭 schema 与精确 comparator。
- 新增 `backend/tests/fixtures/harness/current_capability_profile.v1.json`：
  - `supported`：query、stream event shape；
  - `mapped`：service context、contract version、final result、typed failure；
  - `externalized`：execution ID、control、capability declaration、adapter cancellation；
  - `unsupported`：unexpected exception、terminal cardinality、deadline。
  - ToolGateway 五项当前保证：未注册、非法参数、成功安全记录、敏感输出脱敏、异常中性化；
  - ToolGateway 一项 expected gap：timeout 只结束等待，不取消同步 Tool 执行。
- 新增 `backend/tests/test_harness_runtime_adapter_contract.py`：reference conformance、当前 Runtime profile、声明漂移负向门禁与 ToolGateway 独立边界测试。

### AC 证据

| PRD AC | S2 证明 | 结果 |
|---|---|---|
| AC4 | Reference Adapter 覆盖正常 result、typed failure、带诚实 capability/gap 声明的不支持能力、取消、deadline、完整请求上下文及 0..n event + 恰一 terminal；零/多 terminal、terminal 后输出、未转 typed failure 的意外异常，以及包含敏感值/原始异常的 typed failure message 均被分类拒绝 | PASS |
| AC5 | observed probe 不读取 expected fixture，以真实当前 Coordinator executor 的行为和 `DiagnosisExecutor` 签名推导完整 capability map；与 reviewed v1 fixture 精确比较 | PASS |
| AC6 | 独立 probe 通过真实 ToolGateway 验证未注册、坏 JSON、非对象、缺参数、类型错误均拒绝且执行计数为零；允许请求只执行一次；输出/异常脱敏；timeout 返回后释放受控阻塞 Tool，并确定观察到其继续完成 | PASS |
| AC11（S2） | 错误 terminal 序列、不安全 failure message、Runtime/ToolGateway 未知 key 及 status/gap/locator 漂移均被门禁分类拒绝，承载断言的测试本身通过 | PASS |
| AC12（S2） | 固定 UUID、UTC 时间、fake coordinator/tool；无模型、数据库、主机、日志、用户服务或网络访问 | PASS |
| AC13（S2） | S2 新增套件 `40 passed`，S1+S2 与既有 Runtime/ToolGateway 聚焦 `97 passed`，无 skip/xfail；后端全量 `701 passed` | PASS |
| AC14（S2） | zero-behavior PASS；新增 runtime contract 未被生产入口导入，不修改既有 Runtime、Run service、ToolGateway、DI、API、迁移、前端或依赖 | PASS |
| AC15（S2） | `current_capability_profile.v1.json` 同时记录 Runtime 的 7 个结构化 expected gap、ToolGateway 五项保证和 timeout expected gap；未知 gap、声明失真和 evidence locator 漂移均失败 | PASS |

AC7–AC10 的完整回归证明属于 S3，本轮未宣称完成。

### 验证记录

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_harness_runtime_adapter_contract.py -q
# 40 passed

..\.venv\Scripts\python.exe -m pytest tests/test_harness_contract_kernel.py tests/test_harness_runtime_adapter_contract.py tests/test_p2_application_services.py tests/test_p2_diagnosis_adapter.py tests/test_tool_gateway.py tests/test_agent_gateway.py tests/test_p43_service_context.py -q
# 97 passed

..\.venv\Scripts\python.exe -m ruff check src/domain/harness_contracts.py src/application/runtime_contracts.py tests/support/harness_contracts.py tests/test_harness_contract_kernel.py tests/test_harness_runtime_adapter_contract.py
# All checks passed

..\.venv\Scripts\python.exe -m mypy src/domain/harness_contracts.py src/application/runtime_contracts.py
# Success: no issues found in 2 source files

..\.venv\Scripts\python.exe -m pytest tests -q
# 701 passed, 2 warnings（既有依赖弃用警告）
```

仓库根默认 zero-behavior 校验与 `git diff --check` 均 PASS；generator、baseline 与 S1 Contract Kernel 保持提交版本不变。

### 独立 Review 修订

- 首次独立只读 Review 结论为 `NEEDS_REVISION`：无 P0/P1，发现 3 项 P2 与 1 项 P3。
- P2 修订包括：为 typed failure message 增加 `runtime.stream.failure_message_safety` 安全分类；把 Design §6.1 六项 ToolGateway 事实加入同一封闭版本化 fixture；用受控阻塞 Tool 确定证明网关返回 timeout 后后台执行仍可继续完成，并将其记录为 `tool_gateway.timeout_does_not_cancel_execution` expected gap。
- P3 修订同步了 plan 中 S1 已提交、S2 Review 修订中和 S3 未开始的真实状态。
- 第二轮独立复核关闭了 ToolGateway 与状态文档问题，并指出 failure message oracle 尚漏 API Key、DSN、Windows/POSIX 路径和原始 SQL；修订后参数化覆盖 PRD 安全条款中的凭据/API Key、DSN、路径、原始 SQL、原始异常、Prompt/CoT 与原始 Tool 输出。
- 第三轮独立复核确认无 P0/P1/P2，仅指出新增参数化用例后的验证计数未同步；已按实跑结果修正为 S2 `40 passed`、聚焦 `97 passed`、全量 `701 passed`。
- 最终独立只读确认结论为 `PASS`，无 P0/P1/P2/P3；已关闭问题均无回归。
- 修订仅涉及 S2 新增文件和 Workpack 文档；未修改既有生产文件、generator、baseline 或 S1 已提交文件。S3 仍未开始。
