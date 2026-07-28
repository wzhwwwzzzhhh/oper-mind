# P3 HANDOFF — 主前端工作台

> 更新时间：2026-07-28
> 状态：P3.2c.1 已提交 `5491829`；P3.2c.2 离线核对已完成，真实数据库只读验收按用户决策延后
> 分支：`feat/p3-workbench`　|　当前提交基线：`5491829 feat: 完成P3.2c1 mock FastAPI联调验收`

## 已完成基线

- P2.5、P3 Design、P3.1、P3.2 Design、P3.2a、P3.2b、P3.2c.1 分别提交为 `54f02e5`、`12bed37`、`4862752`、`ec45ee2`、`75d6598`、`3170e6a`、`5491829`。
- P3.2c.1 已完成独立 mock FastAPI / Vite 代理 / 刷新深链人工验收；mock 仅用于本地联调，真实失败不降级为假数据。
- P3.2c.2 已离线确认：URL 优先级、Alembic head `20260726_01_p2`、PostgreSQL 离线 SQL 编译、应用启动不自动迁移。未连接真实 DB/数据源。
- 根 `data/opermind.sqlite3` 存在但为 0 字节、被忽略；未打开或读取，不能用作已迁移或可验收读模型的证据。`config/config.local.yaml` 不存在；当前 Codex 进程没有 `OPERMIND_APP_DATABASE_URL`。不能由此推断用户的 8000 后端目标。

## 后期真实接入门槛（当前不阻塞 P3.3）

用户决定在前后端大致开发完成后再接入真实数据库。届时只有以下全部确认后，才可开始真实只读 API 联调：

```text
C1 应用元数据目标（非诊断数据源）的非密钥标识
C2 受控连接 URL 注入方式（不暴露密钥）
C3 专用只读身份：连接/schema usage/六张 P2 表和 alembic_version 的 SELECT，无 DDL/DML
C4 目标 revision = 20260726_01_p2
C5 安全且可用的 active/archived/Message/Run 验收数据
C6 指定后端实例及其只读身份
C7 五个 GET、cursor、UTC Z、关联 ID、404/归档/分页验收契约
C8 失败即停止、撤销前端代理指向、不以 mock/假数据降级的回退方案
```

详细核对记录见 `step2c2-真实读模型前置条件核对.md`。

以下外部隔离改动禁止读取内容、修改、暂存、提交或 reset：

```text
docs/00-项目方案说明书.md
backend/src/domain/__init__.py
backend/src/infrastructure/persistence/__init__.py
```

后两个初始化文件经 `git diff -- <file>` 核对无内容 diff，仍不得触碰。

## 唯一下一步

**P3.3 Design：Run 受理、幂等与 SSE 恢复。**真实数据库只读验收延后；届时仍须先确认 C1–C8。当前不连接真实 DB 或数据源、不运行在线 Alembic、不修改 8000 后端。
