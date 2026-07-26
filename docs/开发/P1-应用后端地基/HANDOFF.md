# P1 HANDOFF — 应用后端地基

> 更新时间：2026-07-26
> 状态：P1.1a 已提交；P1.1b 已完成并提交
> 分支：`feat/p1-application-foundation`　|　稳定基线：`1559266 chore: 恢复P1环境基线`
> 真实仓库：`D:\market-handsome\oper-mind`

## 当前已完成

- P0 已完成；P0.3 API v1 契约仍是 P1/P2 的实现边界。
- P1.1a 已提交，根 `.venv` 使用 CPython 3.11.9，`backend/requirements.txt` 已安装。
- P1.1b 新增集中式 `backend/src/project_paths.py`，统一定位根 `config/`、`data/`、`experiments/` 与 `backend/`。
- 配置改为从根 `config/config.local.yaml`、根 `config/config.example.yaml` 加载，再由 `OPERMIND_*` 覆盖；`api_key="mock"` fallback 保持可用。
- 后端脚本、pytest 与根评测校验的路径引导已收口；长期记忆默认文件为根 `data/memory.json`。
- 真实验证通过：`pip check`、路径/配置测试、完整 `backend/tests`（87 passed）、API 测试（11 passed）、临时目录的评测校验与 pipeline、mock 健康检查。

## 稳定命令

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

直接脚本可以从任意当前目录通过绝对或仓库相对路径执行；不要以当前目录拼接 `backend/data`、`backend/config` 或 `backend/experiments`。外部遗留调用即使设置 `PYTHONPATH` 也不应改变资源路径解析。

## 未完成与边界

- P1.1b 已提交；后续工作区应从该稳定基线开始。
- 不读取、修改、暂存或提交 `frontend/`、`report/`、`.venv/`、`config/config.local.yaml`、运行时数据或实验产物。
- 不实现 SQLAlchemy、Alembic、ORM、数据库表、Repository、Application Service 或 `/api/v1` 路由。
- 旧 `/diagnose`、`/diagnose/stream` 必须继续兼容。

## 恢复顺序

```powershell
git status --short --branch
git log -5 --oneline
Get-Content -Raw -Encoding UTF8 AGENTS.md
Get-Content -Raw -Encoding UTF8 docs\开发\_A-Plan-总览.md
Get-Content -Raw -Encoding UTF8 docs\开发\_B-V1产品化开发计划.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\HANDOFF.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\design.md
Get-Content -Raw -Encoding UTF8 docs\开发\P1-应用后端地基\step2-配置与数据路径收口.md
git diff --no-ext-diff
```

## 唯一下一步

**P1.1c：应用后端地基设计。**

先依据 P0.3 契约设计 SQLAlchemy/Alembic、SQLite/PostgreSQL 兼容、迁移节奏、Domain/Repository/Application Service 边界与安全降级；未经 Design、Review 和用户授权，不得直接开始数据库实现。

## 必跑验证

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest backend\tests\test_project_paths.py backend\tests\test_eval_config.py -q
.\.venv\Scripts\python.exe -m pytest backend\tests\test_api.py -q
.\.venv\Scripts\python.exe backend\scripts\smoke_pipeline.py
.\.venv\Scripts\python.exe -m pytest backend\tests -q
```

## 提交边界

- 仅暂存 P1.1b 的后端路径/配置实现、对应测试、`data/eval/validate.py`、P1 文档与必要入口/规范同步。
- 禁止 `git add .`；提交前复核 `AGENTS.md` 与 `CLAUDE.md` 字节一致。
- 建议提交信息：`refactor: 收口P1配置与数据路径`。
