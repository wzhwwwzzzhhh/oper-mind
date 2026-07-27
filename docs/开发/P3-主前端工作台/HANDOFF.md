# P3 HANDOFF — 主前端工作台

> 更新时间：2026-07-27
> 状态：P3.2 v1 API 客户端与会话恢复读模型的 Design 与独立审查完成，待用户明确授权暂存/提交
> 分支：`feat/p3-workbench`　|　当前提交基线：`4862752 feat: 初始化P3主前端工程与产品外壳`

## 已完成基线

- P2.5 已提交为 `54f02e5`；P3 Design 已提交为 `12bed37`；P3.1 独立前端工程/产品外壳已提交为 `4862752`。
- `frontend/` 现有 React + TypeScript + Vite、React Router、TanStack Query、Zustand、Ant Design、Vitest/RTL/MSW 基础；`frontend/mockup.html` 保留不动。
- P3.2 Design 已固定 OpenAPI 类型生成、统一 v1 GET client、安全错误/关联元数据、MSW 合同、路由与 Session/Run/Message 的只读刷新恢复顺序。
- 已读取运行中的 `/health` 与 `/openapi.json`。`GET /api/v1/sessions?limit=1` 当前返回安全 `500 INTERNAL_ERROR`；不在本轮修复/绕过，真实 API 验收前需共同确认迁移与持久化环境。

## 当前未提交的 P3.2 Design 精确边界

只允许逐文件暂存：

```text
AGENTS.md
CLAUDE.md
docs/开发/_A-Plan-总览.md
docs/开发/_B-V1产品化开发计划.md
docs/开发/P3-主前端工作台/design.md
docs/开发/P3-主前端工作台/step2-v1-api客户端与会话恢复读模型.md
docs/开发/P3-主前端工作台/review.md
docs/开发/P3-主前端工作台/HANDOFF.md
```

## 必须继续隔离

禁止读取、修改、暂存、提交或 reset：

```text
docs/00-项目方案说明书.md
```

`backend/src/domain/__init__.py` 与 `backend/src/infrastructure/persistence/__init__.py` 经逐文件 `git diff -- <file>` 核对无内容 diff；不得暂存、修改或 reset。P3.2 Design 禁止改动/暂存 `frontend/`、`report/`、`backend/`、`data/`、运行时 SQLite、真实配置和旧 API。

## 提交前验证

```powershell
git diff --check
git diff --name-only
git diff -- AGENTS.md CLAUDE.md
git diff -- docs/开发/P3-主前端工作台
```

核对 AGENTS/CLAUDE hash 一致；确认本轮 diff 不含 `frontend/`、`report/`、`backend/`、`data/` 或外部隔离文档。`/health`/OpenAPI 的本机读取仅为设计输入，不替代 P3.2a/P3.2c 测试。

## 唯一下一步

用户授权后，逐文件暂存上述 P3.2 Design 文档并提交。建议提交信息：`docs: 完成P3.2接口与恢复读模型设计`。**提交后的唯一下一步为 P3.2a：OpenAPI 类型、v1 API 客户端与 MSW 契约实现**；不得混入 Session 工作区、Run 受理、SSE、结果卡或 P4/P5/P6 资源。