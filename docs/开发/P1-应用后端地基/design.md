# P1 设计 — 应用后端地基

> 日期：2026-07-26　|　状态：P1.1a 已提交；P1.1b 已完成并提交　|　稳定基线：`1559266 chore: 恢复P1环境基线`

## 目标

P1 为 V1 产品建立稳定的应用后端基础。先处理环境、路径和配置边界，再进入持久化依赖决策与实现，避免在解释器、导入、数据目录、ORM、Migration 和 API 路由之间混入不确定性。

## 当前固定决策

- 虚拟环境唯一位置为仓库根 `.venv/`；后端依赖唯一输入为 `backend/requirements.txt`。
- 项目资源路径唯一来源为 `backend/src/project_paths.py`：`PROJECT_ROOT`、`BACKEND_ROOT`、`CONFIG_DIR`、`DATA_DIR`、`EXPERIMENTS_DIR` 均由该模块位置解析，不依赖启动目录。
- YAML 配置按根 `config/config.local.yaml`、根 `config/config.example.yaml` 的顺序加载；`OPERMIND_*` 环境变量覆盖 YAML。`api_key="mock"` 继续是确定性 fallback。
- 后端脚本通过 `backend/scripts/_bootstrap.py` 准备根目录与后端导入路径；根 `data/eval/validate.py` 保留一个仅用于直接执行的启动桥接，业务路径仍使用 `src.project_paths`。
- 保持阶段一 `/diagnose`、`/diagnose/stream` 的现有行为，不实现数据库、ORM、迁移、Repository、新 `/api/v1` 路由或 React 工程。

## P1.1 分解

| Step | 名称 | 状态 | 交付与边界 |
|---|---|---|---|
| P1.1a | 环境基线恢复 | 已提交 `1559266` | 根 `.venv`、依赖与 mock 验证；不改业务逻辑 |
| P1.1b | 配置/数据路径收口 | 已提交 | 集中式根路径、配置优先级、脚本/测试跨目录启动；不改 API 行为 |
| P1.1c | 应用后端地基设计 | 下一步 | 先定义 SQLAlchemy/Alembic、SQLite/PostgreSQL、应用层与迁移边界，不实现持久化 |
| P1.1d | 最小应用层落地 | 待开始 | 仅在设计与授权后引入 Domain、Repository、Application Service、Migration 基线 |

## 稳定启动与验证

从仓库根执行：

```powershell
.\.venv\Scripts\Activate.ps1
$env:OPERMIND_API_KEY = "mock"
$env:OPERMIND_BASE_URL = "http://mock"
$env:OPERMIND_MODEL = "mock"

python -m uvicorn --app-dir backend src.app:app --reload
python backend\scripts\smoke_pipeline.py
python data\eval\validate.py
python -m pytest backend\tests -q
```

`uvicorn --app-dir backend` 只解决 `src` 包的导入入口；根配置、数据与实验目录由 `src.project_paths` 固定定位。脚本可用 `python backend\scripts\<name>.py` 从任意当前目录调用。迁移期不再要求全局设置 `PYTHONPATH`，但既有外部调用即使仍设置它也不改变资源目录解析。

## 非目标

- 不读取、修改、暂存或提交 `frontend/`、`report/`、`.venv/`、`config/config.local.yaml`、运行时数据或实验产物。
- 不接入真实数据库、数据源或前后端联调；这些工作需在共同确认目标、最小权限、数据、契约、fallback 与验收场景后开展。
- 不变更阶段一 HTTP/SSE 公开行为。
