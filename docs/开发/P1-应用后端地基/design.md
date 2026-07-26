# P1 设计 — 应用后端地基

> 日期：2026-07-26　|　状态：P1.1a 已完成并通过独立 Review，待用户授权提交　|　稳定基线：`f791e7d`

## 目标

P1 为 V1 产品提供应用后端与持久化地基。本设计先将 P1.1 拆成小步，避免在环境、路径、ORM、Migration、Repository 和 API 路由之间同时引入不确定性。

P1.1a 的唯一目标是恢复一个可重复、可验证的 Python 后端开发环境；它不实现数据库、ORM、迁移、Repository、新 `/api/v1` 路由或 React 工程。

## 当前环境决策

- 虚拟环境唯一位置：仓库根 `.venv/`，已被 `.gitignore` 忽略，不提交。
- 解释器：CPython `3.11.9`，路径为 `C:\Users\35764\AppData\Local\Programs\Python\Python311\python.exe`。
- 后端依赖唯一输入：`backend/requirements.txt`；P1.1a 不引入 SQLAlchemy、Alembic、数据库驱动或未锁定依赖。
- 迁移期从仓库根运行，使用 `PYTHONPATH="$PWD\backend;$PWD"` 同时解析 `backend/src` 与根 `data/` / `config/`；该临时约定由 P1.1b 收口，不能固化为长期产品边界。
- mock 验证显式设置 `OPERMIND_API_KEY=mock`、`OPERMIND_BASE_URL=http://mock`、`OPERMIND_MODEL=mock`；不读取、不提交真实密钥。

## P1.1 分解

| Step | 名称 | 状态 | 交付与边界 |
|---|---|---|---|
| P1.1a | 环境基线恢复 | Review 通过，待提交授权 | 重建 `.venv`、安装锁定依赖、记录实际验证结果；不改业务代码 |
| P1.1b | 配置/数据路径收口 | 待开始 | 收口 `backend/src`、根 `config/`、根 `data/` 的路径与 Settings；保持旧接口兼容 |
| P1.1c | 持久化地基设计与依赖决策 | 待开始 | 依据 P0.3 定义 SQLAlchemy/Alembic、SQLite/PostgreSQL 兼容与迁移边界；先设计后实现 |
| P1.1d | 最小应用层落地 | 待开始 | 仅在前序 Review/授权后引入 Domain、Repository、Application Service、Migration 基线 |

## 固定验证命令

从仓库根执行：

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "$PWD\backend;$PWD"
$env:OPERMIND_API_KEY = "mock"
$env:OPERMIND_BASE_URL = "http://mock"
$env:OPERMIND_MODEL = "mock"

python --version
python -c "import fastapi, pydantic, openai, langgraph, pytest, yaml; print('dependency_imports=ok')"
python -c "from fastapi.testclient import TestClient; from src.app import app; response = TestClient(app).get('/health'); print(response.status_code, response.json())"
python -m pytest backend\tests\test_api.py -q
python backend\scripts\smoke_pipeline.py
```

上述命令使用 mock，保持阶段一 `/diagnose`、`/diagnose/stream` 的当前行为；不执行真实模型或真实数据源。

## 验收

- `.venv\Scripts\python.exe` 指向当前仓库根的 Python 3.11.9 环境，`pip check` 无依赖损坏。
- 锁定依赖可导入，mock 健康检查返回 `200` / `mode=mock`。
- `backend/tests/test_api.py` 与 `backend/scripts/smoke_pipeline.py` 真实通过。
- 工作区不包含 `.venv`、`config/config.local.yaml`、`data/memory.json` 的待提交变化。
- P1.1b 是唯一下一步；本 Step 不修改配置路径实现，只记录其问题。

## 非目标

- 不修改 `backend/` 业务代码、数据库结构、ORM、Migration、Repository、Application Service 或 API 行为。
- 不读取、修改、暂存或提交 `frontend/`。
- 不修改或删除 `report/`。
- 不初始化 React/Vite。

## 文件范围

- `docs/开发/P1-应用后端地基/design.md`
- `docs/开发/P1-应用后端地基/step1-环境基线恢复.md`
- `docs/开发/P1-应用后端地基/HANDOFF.md`
- `docs/开发/_A-Plan-总览.md`
- `docs/开发/_B-V1产品化开发计划.md`
- `AGENTS.md`、`CLAUDE.md`
- `docs/开发/P0-V1产品化基线/step4-主前端产品原型.md`（仅更正验证事实）