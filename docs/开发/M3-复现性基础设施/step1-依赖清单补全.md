# Step 1 — 依赖清单补全

> 日期：2026-07-18
> 快照：工作区未提交；对应 M3 `design.md` §3.4、§4、§5。

## Design

M3 新增 `src/eval/stats.py`，直接依赖 `numpy` 与 `scipy`；测试套件直接依赖
`pytest`。Server Agent 可选使用 `psutil` 获取真实主机指标，虽然缺失时可以稳定
回退到 mock 数据，但为了使真实演示能力可用，应作为标准安装依赖。

当前尚未建立可执行的 Python 虚拟环境，因此不凭空填写未经安装验证的精确版本。
本步骤先声明最低兼容版本；待在干净 `.venv` 中安装、运行 `pytest tests/` 成功后，
再根据该环境将各依赖收敛为精确 `==` 版本。

## Code

- `requirements.txt`
  - 补充直接导入但此前未显式声明的 `pydantic`、`langchain-core`、`typing-extensions`。
  - 补充 `psutil`、`numpy`、`scipy`、`pytest`。
  - 保留 `sqlalchemy`、`pymysql` 为注释状态，因为真实 MySQL 尚未接入。

## Test

待本地 Python 与 `.venv` 创建后执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests -q
```

## Review

- 不包含任何密钥或本地配置。
- 未解除 MySQL 依赖注释，避免安装未使用的功能。
- 未声称已完成安装或测试；当前终端尚未检测到可用的 Python 解释器。

## 验证快照（2026-07-18）

用户在已创建的 Python 3.11.9 `.venv` 中执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

结果：`33 passed, 1 warning in 8.10s`。

随后从该虚拟环境的已安装包元数据读取并锁定了以下直接依赖版本：

- `openai==2.46.0`、`fastapi==0.139.2`、`uvicorn==0.51.0`
- `pydantic==2.13.4`、`langgraph==1.2.9`
- `langchain-openai==1.3.5`、`langchain-core==1.4.9`
- `typing-extensions==4.16.0`、`PyYAML==6.0.3`
- `psutil==7.2.2`、`numpy==2.4.6`、`scipy==1.17.1`
- `pytest==9.1.1`、`fpdf==1.7.2`

唯一警告来自 `tests/test_diagnosis.py:53`：`test_fallback_engine()` 返回布尔值，
Pytest 建议测试函数使用 `assert` 而不是 `return`。这不是测试失败；为了保持本次依赖
锁定改动单一，未在此步骤修改该测试，后续可单独修复并回归验证。

## 后续回归（2026-07-18）

`tests/test_diagnosis.py` 的返回值警告已在后续独立步骤中修复：将执行逻辑抽为
`_run_fallback_engine() -> bool`，由 pytest 测试函数使用 `assert`。最终全量回归为
`34 passed in 3.53s`，无 warning。
