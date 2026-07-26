# P1.1b Step2 — 配置与数据路径收口

> 日期：2026-07-26　|　状态：已完成并提交，独立 Review 通过　|　分支：`feat/p1-application-foundation`　|　基线：`1559266`

## Design

审计发现真实资源位于仓库根 `config/`、`data/` 与 `experiments/`，但旧 `backend/src/config.py`、长期记忆、评测/文档脚本和部分测试把 `backend/` 或当前工作目录误当作项目根。P1.1b 以 `backend/src/project_paths.py` 作为唯一资源路径来源，并以最小启动引导解决直接执行脚本和 pytest 的包导入问题。

配置优先级固定为：根 `config/config.local.yaml` → 根 `config/config.example.yaml` → `OPERMIND_*` 环境变量覆盖。未配置真实密钥时，显式 `OPERMIND_API_KEY=mock`、`OPERMIND_BASE_URL=http://mock`、`OPERMIND_MODEL=mock` 仍可启动确定性 mock 模式。密钥不进入代码、日志或提交。

## Step

1. 从已提交的 P1.1a 基线 `1559266` 恢复，审计 `__file__`、`sys.path`、`data/`、`config/`、`experiments/` 与配置调用点。
2. 新增集中式路径模块与脚本引导，迁移配置加载、长期记忆、评测脚本、文档脚本、pytest 引导与根评测校验脚本。
3. 新增路径/配置测试，覆盖资源目录、根配置选择、环境变量覆盖、mock fallback 与长期记忆默认位置。
4. 从仓库根、`backend/` 和临时工作目录运行真实验证；保持旧 API 与三路 pipeline 回归。

## Code

- `backend/src/project_paths.py`：由模块位置解析仓库根、后端根、根 `config/`、`data/`、`experiments/`，并为已导入后端模块确保根数据包可见。
- `backend/src/config.py`：按根 `config/` 的本地优先、模板兜底顺序加载，再保留既有 `OPERMIND_*` 覆盖。
- `backend/src/memory/long_term.py`：默认记忆文件固定为根 `data/memory.json`，显式传入路径仍受支持。
- `backend/scripts/_bootstrap.py`：后端脚本唯一导入引导；`run_eval.py`、`compare_arms.py`、`check_models.py`、`smoke_pipeline.py`、`generate_human_calibration.py` 与两个 PDF 文档脚本不再假设 `backend/data`、`backend/config` 或 `backend/experiments`。
- `backend/tests/conftest.py`：pytest 的唯一测试导入引导；`backend/tests/test_project_paths.py` 提供针对性覆盖。
- `data/eval/validate.py`：直接执行时仅负责定位仓库与后端包，默认数据文件来自集中式 `DATA_DIR`。

## Test

| 验证 | 实际命令/位置 | 结果 |
|---|---|---|
| 依赖完整性 | 仓库根：`.venv\Scripts\python.exe -m pip check` | 通过，`No broken requirements found.` |
| 路径与配置测试 | 仓库根：`python -m pytest backend/tests/test_project_paths.py backend/tests/test_eval_config.py -q` | `8 passed` |
| 从 backend 执行 | `backend/`：`python -m pytest tests/test_project_paths.py -q` | `4 passed` |
| 根评测校验跨目录 | 临时目录：`python D:\market-handsome\oper-mind\data\eval\validate.py` | 通过，77 条用例合法且与运行时路由一致 |
| API 兼容 | 仓库根：`python -m pytest backend/tests/test_api.py -q` | `11 passed`；仅既有 Starlette/httpx 弃用警告 |
| 三路 pipeline 跨目录 | 临时目录：`python D:\market-handsome\oper-mind\backend\scripts\smoke_pipeline.py` | direct / chain / parallel 与 debate 全部通过 |
| mock 健康检查 | `backend/`：根 `.venv` 执行 `TestClient(app).get('/health')` | `200`，`mode=mock` |
| 完整后端回归 | 仓库根：`python -m pytest backend/tests -q` | `87 passed`；同一既有弃用警告 |
| 评测入口加载 | 临时目录：`python ...\backend\scripts\run_eval.py --help` | 通过；`compare_arms.py` 无参数返回预期用法与非零状态 |

## Review

独立审查见 `review.md`。确认集中式资源目录不依赖当前工作目录、环境变量仍高于 YAML、mock fallback 与阶段一 API 兼容未回归，且没有读取或纳入 `frontend/`、`report/`、`.venv/`、本地配置、运行时数据或实验产物。

## 下一步

唯一下一步为 **P1.1c：应用后端地基设计**。先完成持久化依赖与边界设计；不得直接实现 ORM、迁移、Repository、数据库表或 `/api/v1` 路由。
