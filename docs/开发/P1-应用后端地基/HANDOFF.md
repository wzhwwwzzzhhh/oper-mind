# P1 HANDOFF — 应用后端地基

> 更新时间：2026-07-26
> 状态：P1.1a 环境基线恢复已完成并通过独立 Review，待用户授权提交
> 分支：`feat/p1-application-foundation`　|　稳定基线：`f791e7d feat: 完成P0.4主前端产品原型`
> 真实仓库：`D:\market-handsome\oper-mind`

## 1. 当前已完成

- P0 已完成：产品边界、架构盘点、API v1 契约和主前端 HTML 原型均已提交；P0.3 契约仍是 P1/P2 的实现边界。
- 已从 `feat/p0-product-baseline` 创建并切换到 `feat/p1-application-foundation`。
- 根 `.venv` 已以 CPython 3.11.9 重建，解释器为 `D:\market-handsome\oper-mind\.venv\Scripts\python.exe`。
- 已安装 `backend/requirements.txt`，`pip check`、依赖导入、mock `/health`、`backend/tests/test_api.py`（11 passed）和 `backend/scripts/smoke_pipeline.py` 均已真实通过。
- `.venv/`、`config/config.local.yaml` 与运行时 `data/memory.json` 均未进入工作区 diff 或暂存区。
- 本 Step 未读取、修改、暂存或提交 `frontend/`；未修改或删除 `report/`；未改业务代码、数据库、ORM、Migration、Repository 或 API 行为。

## 2. 可重复环境命令

从仓库根执行：

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "$PWD\backend;$PWD"
$env:OPERMIND_API_KEY = "mock"
$env:OPERMIND_BASE_URL = "http://mock"
$env:OPERMIND_MODEL = "mock"

python --version
python -m pytest backend\tests\test_api.py -q
python backend\scripts\smoke_pipeline.py
```

## 3. 未完成与已知限制

- `backend/src/config.py` 的 YAML 搜索目录仍解析为 `backend/config/`，而仓库模板位于根 `config/`；mock 环境变量当前可覆盖该问题，但不是长期方案。
- `backend/src` 仍需通过 `PYTHONPATH="$PWD\backend;$PWD"` 同时导入 `src` 与根 `data/`；P1.1b 必须收口该运行路径约定。
- 本 Step 只恢复环境；SQLAlchemy、Alembic、SQLite/PostgreSQL、Domain、Repository、Application Service 和 `/api/v1` 实现都未开始。

## 4. 恢复顺序

```powershell
git status --short --branch
git log -5 --oneline
Get-Content -Raw -Encoding UTF8 AGENTS.md
Get-Content -Raw -Encoding UTF8 docs\开发\_A-Plan-总览.md
Get-Content -Raw -Encoding UTF8 docs\开发\_B-V1产品化开发计划.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\HANDOFF.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\design.md
git diff --no-ext-diff
```

确认 `.venv` 仍可用并按本文件的 mock 命令重跑 API smoke 后，进入 P1.1b。

## 5. 唯一下一步

**P1.1b：配置/数据路径收口。**

在不改变阶段一 `/diagnose`、`/diagnose/stream` 行为的前提下，收口 Settings、根 `config/`、根 `data/` 与 `backend/src` 的路径解析；先设计、最小实现、mock 回归、独立 Review，再进入持久化地基设计。

## 6. 提交边界

- 当前待提交仅包括 P1.1a 文档、当前入口同步和 P0.4 验证事实更正。
- 不提交 `.venv/`、`config/config.local.yaml`、`data/memory.json`、凭据、`frontend/`、`report/` 或业务代码。
- 独立 Review 已通过；必须先询问用户是否允许提交，不得自动提交。