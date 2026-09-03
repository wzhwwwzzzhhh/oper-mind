# P10 Harness Contract Kernel · 实施证据

> 日期：2026-09-01
> 当前范围：仅 S1 Contract Kernel；S2 Adapter Contract Test Harness 与 S3 Regression Baseline 尚未开始
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
- S2：未开始。
- S3：未开始。
- 未提交、未推送、未创建 PR。
