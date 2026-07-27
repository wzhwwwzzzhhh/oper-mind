# P3 HANDOFF — 主前端工作台

> 更新时间：2026-07-27
> 状态：P3.2 Design 已提交；P3.2a 已完成 Code / Test / 独立 Review，待用户明确授权暂存/提交
> 分支：`feat/p3-workbench`　|　当前提交基线：`ec45ee2 docs: 完成P3.2接口与恢复读模型设计`

## 已完成基线

- P2.5 已提交为 `54f02e5`；P3 Design 已提交为 `12bed37`；P3.1 独立前端工程/产品外壳已提交为 `4862752`；P3.2 Design 已提交为 `ec45ee2`。
- `frontend/` 保持 React + TypeScript + Vite、React Router、TanStack Query、Zustand、Ant Design、Vitest/RTL/MSW 基础；`frontend/mockup.html` 未修改。`report/` 仍仅为阶段一 Trace 研发界面。
- P3.2a 已新增 OpenAPI 类型生成命令和提交型产物、统一 v1 五个 GET client、Query key/request functions、MSW 契约场景与 8 项客户端测试；没有页面、路由、写操作、SSE 或真实 API 读模型接入。
- 已运行：`npm run typecheck`、`npm test`（2 files / 8 tests）、`npm run build`、`npm run generate:api`，均通过。构建仅保留 Ant Design 主包超过 500 kB 的既有警告。
- 已读取运行中的 `/health` 与 `/openapi.json`。此前 `GET /api/v1/sessions?limit=1` 返回安全 `500 INTERNAL_ERROR`；不在 P3.2a 修复、绕过或以 MSW 掩盖，真实 API 验收仍需确认迁移和持久化环境。

## 当前未提交的 P3.2a 精确边界

只允许逐文件暂存：

```text
AGENTS.md
CLAUDE.md
docs/开发/_A-Plan-总览.md
docs/开发/_B-V1产品化开发计划.md
docs/开发/P3-主前端工作台/design.md
docs/开发/P3-主前端工作台/step2-v1-api客户端与会话恢复读模型.md
docs/开发/P3-主前端工作台/step2a-openapi类型与v1客户端.md
docs/开发/P3-主前端工作台/review.md
docs/开发/P3-主前端工作台/HANDOFF.md
frontend/package.json
frontend/package-lock.json
frontend/src/api/v1/generated.ts
frontend/src/api/v1/client.ts
frontend/src/api/v1/queries.ts
frontend/src/api/v1/client.test.ts
frontend/src/test/handlers.ts
frontend/src/test/server.ts
```

以下是外部隔离改动，禁止读取内容、修改、暂存、提交或 reset：

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
npm run generate:api

Set-Location ..
git diff --check
git diff --name-only
git diff -- AGENTS.md CLAUDE.md docs/开发/P3-主前端工作台 frontend
```

确认 `AGENTS.md` 和 `CLAUDE.md` hash 一致，且暂存清单不包含 `report/`、`backend/`、`data/`、运行时 SQLite 或上述隔离文件。

## 唯一下一步

用户授权后，按精确清单暂存并提交。建议提交信息：`feat: 完成P3.2a v1 API客户端与MSW契约`。

**提交后的唯一下一步为 P3.2b：Session 工作台只读 UI 与刷新/深链恢复实现。**它可消费本 Step 的五个 GET/query key，但不得混入写操作、Run 受理、SSE、完整结果卡、Trace 跳转或 P4/P5/P6 资源。
