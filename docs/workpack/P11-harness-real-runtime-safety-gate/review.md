# P11 Agent Harness 真实运行安全门 · 实现 Review

> 状态：终审 PASS；P0/P1/P2/P3 均无剩余

Reviewer 全程只读，未修改文件，未访问真实外部资源。

## 首轮发现与修复

- P0：无。
- P1：Tool 自身 `TimeoutError` 与 Gateway 等待超时混淆。已以 worker tagged outcome 分离，新增反例断言为 `completed/accepted/completed/error`。
- P1：默认离线门放行 loopback 真实 socket。已改为 collection 前阻断全部 INET 连接、`connect_ex` 和 UDP `sendto`，仅在 thread-local 标记内允许 Python 内部 `socketpair`；新增 loopback 负向探针。
- P1：capability 行为绑定接受硬编码布尔值。已改为 helper 直接运行 guard 探针，并新增必备负向探针 inventory 及删除拒绝用例。
- P2：终止候选后抛 `DiagnosisExecutionError` 分类不准。已改为 invariant violation，并对 result/failure 两种候选增加探针。
- P2：低层拒绝器在 fixture setup 才安装。已改为 `conftest.py` 导入/collection 阶段安装、session finish 恢复。
- P2：Design 仍写“待用户确认”。已更新为 2026-09-03 已明确确认。
- P3：默认 SQLite 按 PID 固定且未清理。已改为 session 唯一 `TemporaryDirectory`，并在 session finish 清理。
- 追加 P1：P10 负向断言及 Workpack manifest 仍可被自身弱化。已锁定 P10 全 7 项用例 inventory、两个关键负向函数的规范化 AST SHA，以及代码固定的 Workpack 3+3 非空互斥路径；删断言、清空/篡改 manifest 的反例均会失败。
- 追加 P2：补齐 base URL/model/action mode 解析、UDP/socketpair 及 PostgreSQL/Redis 主流程 + finalizer 双失败组合证据。
- 主 Agent 自审 P1：发现 legacy/name DNS API 仍可绕过 `getaddrinfo` blocker。已在 collection 前阻断 `gethostbyname/gethostbyname_ex/gethostbyaddr/getnameinfo`，并增加调用即失败探针。
- 主 Agent 自审 P2：并发 `shutdown(cancel_futures=True)` 产生的 `CancelledError` 会落入通用异常并误报 completed。已单独映射为 `completed/closed/cancelled_before_start`，并用可观测执行器证明排队 Tool 调用数为零。
- 主 Agent 自审 P3：`pytest_sessionfinish` 过早撤销 blocker。已取消 undo，改为 blocker 存活到进程退出，临时目录由 `atexit` 清理。
- CI 兼容性修复 P1：阶段门原先对完整 `ast.dump` 取 SHA，Python 3.11 与 3.12 对同一源码的 AST 表示不同，导致 Ubuntu CI 误报内容漂移。已改为统一换行后的完整函数源码 SHA；删除或修改负向断言仍会失败，约束未弱化。
- CI 兼容性修复 P1：P11 manifest 原先记录 Windows checkout 的 baseline/profile CRLF 原始字节，Linux CI 的 LF checkout 因此误报 P10 资产漂移。已改为复用 P10 历史 Git blob SHA；P10 三项资产没有被改写，四集合与历史 blob 双重约束仍拒绝真实内容漂移。

## 修复后复验

- P11 S1：`25 passed`。
- P11 S2：`24 passed`。
- P10/P11 阶段门：`19 passed`。
- loopback 服务注册/API 回归：`16 passed`。
- 自审修复后显式必选合并回归：`203 passed`。
- 自审修复后后端全量：`775 passed`。
- Ruff：`All checks passed!`。
- CI 兼容性修复后：P10/P11 阶段门 `19 passed`，mypy `116 source files` 无问题，后端全量 `775 passed`。
- Git blob 修复后再次复验：P10/P11 阶段门 `19 passed`，Ruff/mypy 通过，后端全量 `775 passed`。

## 终审

Reviewer 只读复核后给出 **PASS**：P0、P1、P2、P3 均无剩余。主 Agent 随后自审发现的 DNS 旁路、concurrent shutdown 错误分类和 blocker 退出尾窗也已修复，并由同一独立 Reviewer 再次只读复核为 **PASS，无剩余 P0–P3**。
