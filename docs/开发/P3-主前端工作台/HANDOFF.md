# P3 HANDOFF — 主前端工作台

> 更新时间：2026-07-27
> 状态：P3.2b 已提交 `3170e6a`；P3.2c.1 已完成 Code / Test / 独立 Review，待用户明确授权暂存/提交
> 分支：`feat/p3-workbench`　|　当前提交基线：`3170e6a feat: 完成P3.2b会话工作台只读恢复`

## 已完成基线

- P2.5、P3 Design、P3.1、P3.2 Design、P3.2a、P3.2b 分别提交为 `54f02e5`、`12bed37`、`4862752`、`ec45ee2`、`75d6598`、`3170e6a`。
- P3.2b 的主产品工作台只从 `/api/v1` 读取 Session、Run、Message；恢复顺序固定为 Session → Runs → Message → Run。没有写操作、Run 受理、SSE/Event、完整结果卡、Trace 跳转或 P4/P5/P6 资源。
- P3.2c.1 新增独立本地 mock FastAPI（默认 8100）和 `VITE_API_PROXY_TARGET` 代理切换。mock 与 MSW 分开；默认开发代理仍为真实后端 8000。
- c.1 浏览器验收通过：根入口、Session 深链 URL 回填、Run 深链刷新、Run 404、安全 500、归档只读、跨 Session Run 阻断和 active cursor。上游 mock 中断时 Vite 返回非 JSON 页面，前端显示 `INVALID_API_RESPONSE`，没有伪造空数据或成功。
- 已通过：`npm run test:mock-api`（4 passed，1 条 TestClient 弃用警告）、`npm run typecheck`、`npm test`（2 files / 12 tests）、`npm run build`。构建仍有 Ant Design 约 732 kB（gzip 约 234 kB）警告。
- 本轮临时 8100 mock、5175 前端和浏览器 tab 均已关闭；用户原有 `5174` 前端与 `8000` 后端保持运行。

## 当前未提交的 P3.2c.1 精确边界

只允许逐文件暂存：

```text
AGENTS.md
CLAUDE.md
docs/开发/_A-Plan-总览.md
docs/开发/_B-V1产品化开发计划.md
docs/开发/P3-主前端工作台/design.md
docs/开发/P3-主前端工作台/step2-v1-api客户端与会话恢复读模型.md
docs/开发/P3-主前端工作台/step2c1-mock-fastapi联调验收.md
docs/开发/P3-主前端工作台/review.md
docs/开发/P3-主前端工作台/HANDOFF.md
frontend/package.json
frontend/vite.config.ts
frontend/src/test/handlers.ts
frontend/scripts/mock_v1_api.py
frontend/scripts/test_mock_v1_api.py
```

以下为外部隔离改动，禁止读取内容、修改、暂存、提交或 reset：

```text
docs/00-项目方案说明书.md
backend/src/domain/__init__.py
backend/src/infrastructure/persistence/__init__.py
```

后两个初始化文件经 `git diff -- <file>` 核对无内容 diff，仍不得触碰。

## 提交前验证

```powershell
Set-Location frontend
npm run test:mock-api
npm run typecheck
npm test
npm run build

Set-Location ..
git diff --check
git diff --name-only
```

确认镜像规则文件 hash 一致，且暂存清单不包含 `report/`、`backend/`、`data/`、运行时 SQLite 或上述隔离文件。

## 唯一下一步

用户授权后，按精确清单暂存并提交。建议提交信息：`feat: 完成P3.2c1 mock FastAPI联调验收`。

**提交后的唯一下一步为 P3.2c.2：真实读模型前置条件核对。**只确认迁移、连接目标、最小权限、可用 mock 数据、接口契约、回退路径与验收场景；未共同确认前不得连接真实 DB 或数据源。
