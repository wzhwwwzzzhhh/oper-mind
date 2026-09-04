# P12 PostgreSQL、Redis 与 MySQL 真实只读接入 · 实现 Review

> 状态：独立只读代码 Review PASS；P0/P1/P2/P3 均为 0

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

## 最终结论

实现 Review 已 PASS，可进入 deliver。Workpack 仍保持 active：AC14 的三个真实目标验收未获逐目标当次授权、未执行，因此 P12 不标记完成、不归档、不关闭 Issue。
