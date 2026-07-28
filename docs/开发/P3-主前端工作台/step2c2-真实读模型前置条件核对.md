# P3.2c.2 Step — 真实读模型前置条件核对

> 日期：2026-07-28　|　状态：✅ 离线核对完成；按用户决策延后真实数据库只读验收；未连接真实 DB 或数据源
>
> 分支：`feat/p3-workbench`　|　实现基线：`5491829 feat: 完成P3.2c1 mock FastAPI联调验收`

## 1. 目标与严格边界

本 Step 的目标是为后续真实 `/api/v1` **只读**验收建立可审查的连接前置条件。只核对配置、迁移、最小权限、可用数据、契约、回退与验收场景；不执行任何真实连接、查询、迁移、写入、数据创建、数据源接入或认证改造。

- 不读取 `config/config.local.yaml`、`.env`、运行中服务的环境变量、进程命令行中的连接串或数据库内容；
- 不打开、连接或读取根 `data/opermind.sqlite3`；
- 不运行 `alembic upgrade head` 在线模式，不变更真实 schema；
- 不修改 `backend/`、`report/`、`data/`、`frontend/mockup.html`、P2 `/api/v1`、旧 API 或前端业务页面。

## 2. 已离线确认的事实

| 项目 | 结论 | 证据/含义 |
|---|---|---|
| URL 优先级 | 已确认 | `OPERMIND_APP_DATABASE_URL` > 被忽略的 `config/config.local.yaml` 中 `persistence.database_url` > 根 `data/opermind.sqlite3` |
| 当前 Codex 进程 URL | 未设置 | 本进程没有 `OPERMIND_APP_DATABASE_URL`；不能据此推断用户运行的 8000 后端使用什么目标 |
| 本地配置 | 不存在 | `config/config.local.yaml` 不存在；按规则没有读取任何本地密钥文件 |
| 默认 SQLite | 不可作为证据 | 根 `data/opermind.sqlite3` 存在但为 0 字节、被 `.gitignore` 忽略；本 Step 未打开它，不能假定已迁移或含可验收数据 |
| 迁移 head | 已确认 | 唯一业务 revision 为 `20260726_01_p2`；创建 Session、Message、DiagnosisRun、RunEvent、DiagnosisResult、idempotency 六张 P2 表 |
| PostgreSQL 兼容性 | 已离线确认 | `postgresql+psycopg` 方言 `alembic upgrade head --sql` 编译通过；未建立网络连接 |
| 自动 schema 变更 | 已确认禁止 | `build_v1_services()` 只装配 persistence runtime；应用启动不调用 `create_all()` 或 Alembic 自动升级 |
| 现有真实 API | 未重新连接 | 历史观察为 8000 的 `GET /api/v1/sessions` 返回安全 `500 INTERNAL_ERROR`；c.2 不读取日志或修复根因 |
| mock 回退 | 已确认 | P3.2c.1 mock 仅用于独立联调；真实读模型失败时主产品不得静默切换到 mock/假数据 |

## 3. 连接前必须由用户/数据库所有者确认的清单

| 编号 | 必须确认 | 通过标准 | 本 Step 当前状态 |
|---|---|---|---|
| C1 | 应用元数据目标 | 提供**非密钥**目标标识：DB 类型、环境、主机/服务别名、库名；确认不是诊断数据源、不是生产业务数据源 | 待确认 |
| C2 | 注入方式 | 用户自行在启动后端的受控环境配置 `OPERMIND_APP_DATABASE_URL` 或本地配置；不得在聊天、文档、Git 或命令输出暴露密码/token | 待确认 |
| C3 | 最小权限 | 本轮真实读取使用专用只读身份：仅需连接、schema usage、`alembic_version` 与六张 P2 表的 SELECT；无 DDL、DML、superuser、跨库权限 | 待确认 |
| C4 | 迁移版本 | 数据库所有者确认目标实例 current revision 为 `20260726_01_p2`；若不是 head，停止联调，由所有者在受控变更流程中迁移 | 待确认 |
| C5 | 可用且安全的验收数据 | 至少存在一个可读取的 active Session；建议另有 archived Session、关联 Message/Run 和一个不存在 ID 的安全 404 场景。数据不得含凭证、真实客户隐私或敏感 Trace | 待确认 |
| C6 | API 部署目标 | 指定要联调的后端实例（当前 8000 或独立受控实例），确认其使用 C1/C3 的只读身份；前端仍只走 Vite `/api` 代理 | 待确认 |
| C7 | 契约与验收 | 明确五个 GET、cursor、UTC `Z`、安全 error、`X-Request-Id`/`X-Trace-Id`；验收含根入口、Session/Run 深链刷新、404、归档、空/分页 | 待确认 |
| C8 | 回退与停止条件 | 任一连接/权限/迁移/数据/契约不符合即停止真实联调，撤销该实例的前端代理指向并恢复到不连接状态；不得以 mock 填补真实失败 | 待确认 |

## 4. 允许的后续执行顺序（仅在 C1–C8 全部确认后）

```text
用户/DB 所有者确认目标与只读权限
→ 用户在受控环境注入连接 URL（不发送密钥）
→ 数据库所有者确认 revision = 20260726_01_p2
→ 启动独立、只读后端实例
→ 仅 GET /api/v1 Session / Runs / Messages / Run
→ 前端经 Vite /api 代理做根入口、深链、刷新、404、归档、cursor 验收
→ 记录 request/trace 关联与安全回退
→ 关闭临时实例，完成 Review
```

禁止在此序列中创建 Session/Run、执行 POST/PATCH/DELETE、运行 SSE、应用迁移、修改数据库账号、读取诊断数据源或接入 P3.3/P3.4/P4/P5/P6。

## 5. 延后决策与后续门槛

用户已决定：**真实数据库只读验收延后到前后端大致开发完成后再启动。**因此本 Step 以离线核对完成收口，不等待 C1–C8，也不尝试连接当前 `8000` 后端。

C1–C8 仍是后期真实接入的强制门槛：届时必须由用户/数据库所有者确认应用元数据目标、受控 URL 注入、专用只读权限、revision `20260726_01_p2`、安全验收数据、后端实例、五个 GET 契约与停止/回退方案；任一条件不成立即停止，不以 mock 或假数据伪造真实成功。

**当前唯一下一步为 P3.3 Design：Run 受理、幂等与 SSE 恢复。**P3.3 Design 仍不连接真实 DB 或数据源。
