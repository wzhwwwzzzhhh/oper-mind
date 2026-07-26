# P1.1a Step1 — 环境基线恢复

> 日期：2026-07-26　|　状态：已完成并提交　|　分支：`feat/p1-application-foundation`　|　关联 commit：`1559266 chore: 恢复P1环境基线`

## Design

P0.2 已记录根 `.venv\Scripts\python.exe` 无法启动，P1 不能在解释器失效、依赖不可验证的状态下开始持久化地基。P1.1a 先恢复环境，不通过修改业务逻辑、跳过测试或使用未记录的全局依赖掩盖问题。

目标环境固定在仓库根 `.venv`，解释器选用已盘点到的 CPython 3.11.9。后端依赖只从 `backend/requirements.txt` 安装，mock 模式通过环境变量显式注入，避免本 Step 改动现有 `backend/src/config.py` 路径逻辑。

## Step

1. 按 P0 交接顺序确认工作区干净、P0 已收口并创建 `feat/p1-application-foundation`。
2. 只读盘点系统 Python、旧 `.venv` 配置、依赖输入、配置加载和 smoke/API 测试脚本。
3. 删除已确认失效的根 `.venv`，以 Python 3.11.9 在当前仓库根重建并安装 `backend/requirements.txt`。
4. 从仓库根设置明确的 `PYTHONPATH` 和 mock 环境变量，执行版本、依赖导入、健康检查、API smoke 与三路 pipeline。
5. 记录实际结果和未解决的路径问题；P1.1b 才修改配置/数据路径实现。

## Code

- 无业务代码、API、数据库、ORM、Migration、Repository 或 React 改动。
- 环境资产：根 `.venv/` 重建为当前仓库环境，因 `.gitignore:2` 忽略而不进入暂存。
- `docs/开发/P0-V1产品化基线/step4-主前端产品原型.md`：把不准确的“直接检查 HTML”表述修正为真实执行的“提取内嵌脚本后运行 `node --check`”。

## Test

| 验证 | 实际命令/操作 | 结果 |
|---|---|---|
| 系统 Python | `py -0p`、Python 3.10/3.11 `--version` | 发现 Python 3.10.11、3.11.9；选择 3.11.9 |
| 旧 venv 根因 | 读取 `.venv/pyvenv.cfg` | 旧 `command` 指向 `D:\market-handsome\newproject\oper-mind\.venv`，启动器失效 |
| 重建环境 | Python 3.11.9 `-m venv .venv` + `pip install -r backend\requirements.txt` | 成功；pip 升级至 26.1.2，锁定依赖安装完成 |
| Python/依赖 | `.venv\Scripts\python.exe --version`；导入 fastapi/pydantic/openai/langgraph/pytest/yaml | Python 3.11.9，`dependency_imports=ok` |
| 依赖完整性 | `.venv\Scripts\python.exe -m pip check` | `No broken requirements found.` |
| mock 配置与根数据导入 | 设置 `PYTHONPATH`、三项 mock 环境变量后导入 `src.config`、`data.scenarios` | `config_mode=mock`、`scenario_import=ok` |
| 健康检查 | `TestClient(app).get('/health')` | `200`，`{'status': 'ok', 'mode': 'mock', 'model': 'mock'}` |
| API smoke | `python -m pytest backend\tests\test_api.py -q` | `11 passed`，1 条 Starlette/httpx 弃用警告 |
| pipeline smoke | `python backend\scripts\smoke_pipeline.py` | direct / chain / parallel 与 debate 分支全部通过 |

所有验证从仓库根运行并设置：

```powershell
$env:PYTHONPATH = "$PWD\backend;$PWD"
$env:OPERMIND_API_KEY = "mock"
$env:OPERMIND_BASE_URL = "http://mock"
$env:OPERMIND_MODEL = "mock"
```

验证后 `data/memory.json` 没有待提交 diff；`.venv/` 和 `config/config.local.yaml` 均已被 `.gitignore` 忽略。

## Review

- 已完成独立审查并于 `1559266` 提交；环境结论可复现、所有通过结果来自实际命令、ignored 环境资产或敏感配置未进入暂存，且未改动业务代码与前端资产。
- 当前已知限制：`backend/src/config.py` 仍向 `backend/config` 查找 YAML，而模板位于根 `config/`；本 Step 用环境变量覆盖并记录问题，不修改实现。
- 唯一下一步：P1.1b 配置/数据路径收口。