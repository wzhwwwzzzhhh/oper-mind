# P12 PostgreSQL、Redis 与 MySQL 真实只读接入 · 实现 Review

> 状态：PR #126 已合并；合并后收口复核 PASS；P0=0、P1=0、P2=0、P3=0；AC14 真实验收仍待执行

Reviewer 必须只读，不修改文件，不访问真实外部资源。所有 P0/P1/P2 必须修复并重新验证；P3 也应修复或明确为不阻塞遗留。

## Review 发现

Reviewer 全程只读、未修改文件、未访问真实服务或模型。严格审查共经历四轮收敛：

- 首轮：P0=0、P1=5、P2=5、P3=0。主要涉及 PG capability/intent 半接入、binding contract、Registry 原子可见性、缺正式 E2E、Runner 异常、cleanup/fact、迁移/UI/stage/timeout 负证据不足。
- 二轮：P0=0、P1=2、P2=5、P3=0。主要涉及 Runner PG 选错 Tool、bound Tool 被 scenario 截走、全量投影 barrier、generic connection、typed failure/fact、正式装配负向矩阵与 cleanup 语义。
- 三轮：P0=0、P1=2、P2=1、P3=0。发现 bound lock 数据库范围、Runner 未消费 Tool 事实、driver 包装异常分类。
- 最终 spot review 前：P0=0、P1=0、P2=2、P3=0。只剩 current_database 异常值 fail-open 与 psycopg SQLSTATE 分类。
- 最终结论：**PASS；P0=0、P1=0、P2=0、P3=0**。

## 修复与复验

- PG 保留既有慢查询 Tool 并增加 health intent；entry 暴露前做 exact kind/investigation/capability profile 校验。
- Registry 增加 per-service guard、mutation epoch barrier、identity-CAS 与 poison 隔离；typed binding failure 覆盖 not-found/type/investigation/credential/poison。
- PG Agent capability 收窄为类型限定 adapter；bound Tool 不读全局 scenario、不暴露 connection/engine，lock Tool 无模型 database 参数并强制 current_database 范围；范围事实 malformed 时后续 lock SQL 零调用。
- Runner 按 kind 精确选择 health Tool，严格消费 exact allowlist JSON，生成事实型安全 Result，并在退出成功前核对 succeeded、唯一终态、唯一成功 Tool、精确 service_id 与 Result 安全投影。
- Redis/MySQL 固定命令/SQL、required fact、timeout/permission/malformed/cleanup taxonomy 收敛；三类 Connector 能识别异常 wrapper、MySQL driver code 与 psycopg SQLSTATE，且不读取异常正文。
- 正式装配 E2E、迁移 previous→upgrade/unsafe downgrade/non-SQLite spy、前端 exact service_id/intent、stage mutation 和 timeout-map 负探针均补齐。
- Reviewer 最终只读复验：相关 P12、P12 gate、P11 Runtime/ToolGateway `89 passed, 1 warning`；`git diff --check` 通过。

## PR #126 外部审查返修

外部审查发现 `P1=1、P2=2`，均按阻塞项处理，没有放宽 Design、门禁或断言：

- **P1 PostgreSQL health Tool 菜单**：exact health default query 现在由服务端在 Graph 路由前固定为 `direct/db`；DBAgent 为该 query 构造独立 active Tool registry，只暴露 `check_connection_pool`，ToolGateway 也只持有该 registry；本次健康调查最多接纳一次 Tool 调用。负向 driver 同一响应请求两次时，底层只执行一次；普通 PostgreSQL 调查仍保留原受限 Tool 菜单。
- **P2 MySQL 部分指标假健康**：Connector 要求 `Uptime/Threads_connected/Threads_running/Slow_queries/max_connections` 精确齐全；缺失时快照为 `unavailable/malformed_fact`，Agent Tool unavailable，`ServiceRegistrationApplicationService.test_connection()` 也返回 unavailable。
- **P2 Runner 核心编排证据**：Runner 拆出可注入、默认仍延迟真实装配的 runtime loader。临时 SQLite + fake Redis connector 的离线测试已完整进入 Registry/origin、连接测试、服务 Session、Run、唯一 Tool/终态、Trace/Result 校验；另证明 origin mismatch 在连接测试前停止。

返修聚焦与回归：`57 passed`、P12 全组 `88 passed`、P10/P11/P12 历史矩阵 `158 passed`；后端全量 `866 passed`，Ruff、Mypy 和 P12 exact-path gate 通过。

## 合并前自审

在外部审查返修提交 `8b59cb6` 上重新从执行边界审查，不沿用返修前结论：

- PostgreSQL canonical health query 在服务端 Graph 进入模型路由前固定为 `direct/db`；DBAgent 以同一个 domain constant 选择独立 health registry，模型 schema 与 ToolGateway 实际 registry 均只有 `check_connection_pool`，并在第二次 Tool 接纳前停止。前端 `intent` 仍只是 UX token，不成为授权参数；编辑后的普通文本不冒充 canonical health profile，目标与能力继续由 Session/Run `service_id` 和 typed binding 决定。
- MySQL Connector 在构造 healthy snapshot 前要求五个固定指标集合精确相等；缺失、重复、非数值或额外指标均收敛为 typed unavailable。服务中心连接测试与 Agent Tool 都读取同一 snapshot 语义，不再出现“连接正常、Tool 拒绝”的矛盾状态。
- 人工 Runner 的离线测试通过注入的 runtime loader 进入完整 `run_acceptance()` 编排，使用临时 SQLite 的正式 Registry、ServiceRegistration、ServiceCenter、Session/Run/Event/Result repositories 与 deterministic driver；覆盖 origin 匹配、连接测试、唯一 Tool/终态和安全 Result 校验，并证明 origin 不匹配时在服务访问前停止。默认 loader 仍是延迟生产装配，普通测试不会访问真实目标。
- 全量变更范围未触碰 `tests/conftest.py`、P10/P11 baseline、生成 OpenAPI 或 Design 禁止文件；未增加 skip/xfail/xpass，未发现凭据、目标或原始异常泄漏，也未扩大到任意 SQL、任意 Redis 命令、写能力或额外服务类型。

自审结论：**PASS；P0=0、P1=0、P2=0、P3=0**。该结论只解除 PR 合并的软件门，不替代 AC14 的逐目标人工授权与真实验收。

## 合并后收口复核

PR #126 合并后从 ServiceCenter → Workbench → Run 的真实用户路径重新检查，发现 canonical health intent 虽已预填固定问题，但仍复用了普通可编辑 Composer。该路径既可能把固定问题作为普通 Message 发送，也可能在用户编辑后失去服务端 exact-query health profile，因而不能把既有 AC17 UI 证据视为完整闭环。

收口修复将该 intent 改为显式固定动作：仅当当前单服务会话的权威服务投影声明 `service_health_pressure.v1` 时展示，并直接调用 Run 创建路径；前端不允许编辑 canonical query。直接伪造 intent URL、服务未声明 capability、服务列表加载失败或会话绑定不唯一时均不启动。若已有其他待恢复发送意图，页面要求先恢复或明确丢弃，不复用其问题或幂等键。成功受理并恢复服务端记录后，URL intent 被 replace 清除，回到普通会话录入。

新增测试覆盖精确 Run payload、普通 Message 零调用、未声明 capability 失败关闭、旧发送意图冲突与未知 intent；聚焦 `4 passed`，前端全量 `22 files / 224 tests passed`，typecheck、production build、P12 gate 与 `git diff --check` 均通过。收口复核结论：**PASS；P0=0、P1=0、P2=0、P3=0**。

## 最终结论

三项外部审查问题已完成返修、回归与合并前自审，可以合并 PR。Workpack 仍保持 active：AC14 的三个真实目标验收未获逐目标当次授权、未执行，因此 P12 不标记完成、不归档、不关闭 Issue。
