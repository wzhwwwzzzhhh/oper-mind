# P3 HANDOFF — 主前端工作台

> 更新时间：2026-07-26
> 状态：P3.1 前端工程初始化与产品外壳已完成并提交；P3.2 Design 待开始
> 分支：`feat/p3-workbench`　|　当前提交基线：`12bed37 docs: 完成P3主前端工作台设计`

## 已完成

- P3 Design 已提交为 `12bed37`；P2.5 已提交为 `54f02e5`。
- `frontend/` 已建立独立 `opermind-workbench` React + TypeScript + Vite 工程；P0 `mockup.html` 保留不动。
- 已装配 React Router、TanStack Query、Zustand、Ant Design、Vitest/RTL/MSW 和 `/workbench` 产品外壳。
- 页面只显示真实空状态与 P4/P5/P6 诚实边界；未调用 `/api/v1` 或旧接口，未伪造 Session/Run/结果。
- 已通过 Node 22.23.1/npm 10.9.8 下的 typecheck、Vitest（1 passed）、production build 和本地视觉/导航验收。

## P3.1 历史提交边界

只允许逐文件暂存：

```text
AGENTS.md
CLAUDE.md
frontend/.gitignore
frontend/index.html
frontend/package.json
frontend/package-lock.json
frontend/tsconfig.json
frontend/tsconfig.app.json
frontend/tsconfig.node.json
frontend/vite.config.ts
frontend/src/main.tsx
frontend/src/app/App.tsx
frontend/src/app/App.test.tsx
frontend/src/app/providers.tsx
frontend/src/features/workbench/WorkbenchPage.tsx
frontend/src/stores/use-ui-store.ts
frontend/src/styles/global.css
frontend/src/test/server.ts
frontend/src/test/setup.ts
docs/开发/_A-Plan-总览.md
docs/开发/_B-V1产品化开发计划.md
docs/开发/P3-主前端工作台/design.md
docs/开发/P3-主前端工作台/step1-前端工程初始化与产品外壳.md
docs/开发/P3-主前端工作台/review.md
docs/开发/P3-主前端工作台/HANDOFF.md
```

## 必须继续隔离

禁止读取、修改、暂存、提交或 reset：

```text
docs/00-项目方案说明书.md
```

`backend/src/domain/__init__.py` 与 `backend/src/infrastructure/persistence/__init__.py` 经逐文件 `git diff -- <file>` 核对无内容 diff；不得暂存、修改或 reset。禁止暂存/改动 `report/`、`backend/`、`data/`、真实配置、运行时 SQLite 和旧 API。`frontend/node_modules/`、`frontend/dist/`、coverage 和本地日志由 `frontend/.gitignore` 忽略，不得人工加入版本控制。

## 已执行验证

```powershell
Set-Location frontend
npm run typecheck
npm test
npm run build
Set-Location ..
git diff --check
git diff --name-only
git diff --cached --check
```

核对 AGENTS/CLAUDE hash 一致，确认 staged diff 仅为上述文件；保留 Ant Design 初始包体超过 500 kB 的 Vite 提示为非阻塞性能观察项。

## 唯一下一步

P3.1 将按上述精确边界提交；提交信息为 `feat: 初始化P3主前端工程与产品外壳`。**提交后的唯一下一步为 P3.2：v1 API 客户端与会话恢复读模型的 Design**；不得混入 Run 受理、SSE、结构化结果或 P4/P5/P6 资源。