# P3 HANDOFF — 主前端工作台

> 更新时间：2026-07-27
> 状态：P3.2a 已提交；P3.2b 已完成 Code / Test / 独立 Review，待用户明确授权暂存/提交
> 分支：`feat/p3-workbench`　|　当前提交基线：`75d6598 feat: 完成P3.2a v1 API客户端与MSW契约`

## 已完成基线

- P2.5 已提交为 `54f02e5`；P3 Design 已提交为 `12bed37`；P3.1 产品外壳已提交为 `4862752`；P3.2 Design 已提交为 `ec45ee2`；P3.2a 已提交为 `75d6598`。
- `frontend/` 保持 React + TypeScript + Vite、React Router、TanStack Query、Zustand、Ant Design、Vitest/RTL/MSW；`frontend/mockup.html` 未修改。`report/` 仍仅为阶段一 Trace 研发界面。
- P3.2b 已增加 `/workbench`、Session、Run 深链的只读 UI，恢复 active Session、Session、Run、Message、选定 Run；MSW 页面测试锁定 Session → Runs → Message → Run 请求顺序。
- 页面在 Run 与当前 Session 不匹配时显示安全 `RUN_SESSION_MISMATCH`；已持久化 result 只说明待 P3.4 展示；无写操作、Run 受理、SSE、Event、Trace 跳转或 P4/P5/P6 资源。
- 已运行：`npm run typecheck`、`npm test`（2 files / 12 tests）、`npm run build`，均通过。构建保留 Ant Design 主包约 732 kB（gzip 约 234 kB）的警告。
- 人工验收：本机 `http://[::1]:5174/workbench` 的真实后端读取仍收到安全 `INTERNAL_ERROR`；页面展示错误码、通用消息和 request ID，不伪造 Session。MSW 成功恢复路径已由页面测试覆盖；这不等于真实 API 成功。

## 当前未提交的 P3.2b 精确边界

只允许逐文件暂存：

```text
AGENTS.md
CLAUDE.md
docs/开发/_A-Plan-总览.md
docs/开发/_B-V1产品化开发计划.md
docs/开发/P3-主前端工作台/design.md
docs/开发/P3-主前端工作台/step2-v1-api客户端与会话恢复读模型.md
docs/开发/P3-主前端工作台/step2a-openapi类型与v1客户端.md
docs/开发/P3-主前端工作台/step2b-session工作台只读恢复.md
docs/开发/P3-主前端工作台/review.md
docs/开发/P3-主前端工作台/HANDOFF.md
frontend/src/api/v1/client.ts
frontend/src/api/v1/client.test.ts
frontend/src/app/App.tsx
frontend/src/app/App.test.tsx
frontend/src/features/workbench/WorkbenchPage.tsx
frontend/src/features/workbench/resource-readers.ts
frontend/src/styles/global.css
frontend/src/test/handlers.ts
frontend/vite.config.ts
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
npm run typecheck
npm test
npm run build

Set-Location ..
git diff --check
git diff --name-only
```

确认 `AGENTS.md` 和 `CLAUDE.md` hash 一致，且暂存清单不包含 `report/`、`backend/`、`data/`、运行时 SQLite 或上述隔离文件。

## 唯一下一步

用户授权后，按精确清单暂存并提交。建议提交信息：`feat: 完成P3.2b会话工作台只读恢复`。

**提交后的唯一下一步为 P3.2c：mock FastAPI 联调、刷新/深链人工验收与真实读模型前置条件核对。**真实 API 读取前必须共同确认迁移、连接目标、最小权限、可用 mock 数据、回退路径和验收场景；不得把当前安全 500 解释为前端可降级为假数据的条件。
