# P3 HANDOFF — 主前端工作台

> 更新时间：2026-07-26
> 状态：P3 Design 与独立审查完成，待用户明确授权暂存/提交
> 分支：`feat/p3-workbench`　|　设计基线：`54f02e5 feat: 完成P2.5刷新恢复与闭环验收`

## 已完成

- 已核实 P2.5 提交为 `54f02e5`，计划、规则镜像和 P2 历史交接已校正为已提交。
- `frontend/` 仅有 P0 `mockup.html`，没有正式工程；`report/` 保持独立研发/Trace 前端。
- `design.md` 已固定工程策略、外壳、v1 API、刷新/SSE、空错状态、report 边界、测试/联调、风险和 Step 分解。
- `review.md` 已完成独立审查；本轮未安装依赖、初始化前端或改业务代码。

## 精确暂存边界

仅逐文件暂存：

```text
AGENTS.md
CLAUDE.md
docs/开发/_A-Plan-总览.md
docs/开发/_B-V1产品化开发计划.md
docs/开发/P2-会话诊断闭环/design.md
docs/开发/P2-会话诊断闭环/HANDOFF.md
docs/开发/P2-会话诊断闭环/review.md
docs/开发/P2-会话诊断闭环/step5-刷新恢复与闭环验收.md
docs/开发/P3-主前端工作台/design.md
docs/开发/P3-主前端工作台/step1-前端工程初始化与产品外壳.md
docs/开发/P3-主前端工作台/review.md
docs/开发/P3-主前端工作台/HANDOFF.md
```

## 必须隔离

不得读取、修改、暂存、提交或 reset：`docs/00-项目方案说明书.md`。`backend/src/domain/__init__.py` 与 `backend/src/infrastructure/persistence/__init__.py` 经逐文件 `git diff` 核对无内容 diff；不得暂存、修改或 reset。禁止改动/暂存 `frontend/`、`report/`、`backend/`、`data/`、运行时 SQLite、真实配置和旧 API。

## 提交前验证与下一步

运行 `git diff --check`、`git diff --name-only`，核对 AGENTS/CLAUDE hash 相同，确认 diff 不含 `frontend/`、`report/`、`backend/`、`data/` 或外部隔离文档。建议提交信息：`docs: 完成P3主前端工作台设计`。

**提交后的唯一下一步为 P3.1：前端工程初始化与产品外壳。**