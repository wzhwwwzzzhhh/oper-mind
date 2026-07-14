# M0 · Step3 — build_system 去重（抽取 bootstrap）

## Design 层

### 为什么抽
`src/app.py`（FastAPI 入口）和 `src/main.py`（CLI 入口）各自维护了一份**逐字重复**的 `build_system()`：读取配置、构建 `LLMClient`、装配三个领域 Agent（db/server/log）、装配质量保障组件（Debate/Reflection/Report），再注入 `CoordinatorAgent` 并注册 Agent。

两份逻辑完全一致（仅注释略有差异），带来的问题：
- **双份维护成本**：装配链路一旦变动（新增 Agent、调整依赖注入），要同步改两处，极易漏改。
- **一致性风险**：两个入口构建出的系统若不小心走偏，行为就会分叉。
- **违反单一职责**：入口文件本该只关心「入口」（HTTP 路由 / CLI 交互），不该承担系统装配职责。

### 方案
新建 `src/core/bootstrap.py`，作为唯一的「系统装配」模块，暴露 `build_system() -> CoordinatorAgent`。两个入口均 `from src.core.bootstrap import build_system`，各自按需调用：
- `app.py`：保留模块级单例 `coordinator = build_system()`。
- `main.py`：在 `main()` 内调用 `coordinator = build_system()`。

### 取舍
- **放在 `core/` 而非新建顶层模块**：装配逻辑依赖 core 与 agents，归入 `core/` 语义自洽，且与 `coordinator.py`、`llm.py` 同层，便于查找。
- **保持行为零变更**：仅搬移位置，不动构建逻辑；默认 model 仍为 `"qwen2.5:7b"`，依赖注入顺序、注册 key 全部不变。
- **`load_config` 依旧从 `src.config` import**：config.py 正由另一 agent 改造（环境变量读取），但其签名与返回结构不变，故 bootstrap 不受影响，也不触碰 config.py。

---

## Step 层

1. 读取 `app.py`、`main.py` 现有 `build_system()`，确认两者逻辑一致。
2. 新建 `src/core/bootstrap.py`，搬入构建逻辑，补中文 docstring 与返回类型标注 `-> CoordinatorAgent`，保留分组注释（领域 Agent / 质量保障组件 / Coordinator）。
3. 改 `app.py`：删除本地 `build_system()`，改为 import；清理仅服务于 build_system 的无用 import；保留模块级 `coordinator = build_system()`。
4. 改 `main.py`：删除本地 `build_system()`，改为 import；清理无用 import；`main()` 内继续调用。
5. 验证两个入口可正常 import 且构建成功。
6. 记录本开发日志。

---

## Code 层

### bootstrap.py 核心（`src/core/bootstrap.py:18`）
```python
def build_system() -> CoordinatorAgent:
    """构建整个系统，注入所有依赖，返回已接通质量保障链路的 Coordinator"""
    config = load_config()
    llm_config = config["llm"]

    llm = LLMClient(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model=llm_config.get("model", "qwen2.5:7b"),
    )

    # 领域 Agent
    db_agent = DBAgent(llm=llm)
    server_agent = ServerAgent(llm=llm)
    log_agent = LogAgent(llm=llm)

    # 质量保障组件
    debate = DebateArena(llm=llm)
    reflection = ReflectionEngine(llm=llm)
    report = ReportAgent()

    # Coordinator：持有编排图，注入领域 Agent 与质量保障组件
    coordinator = CoordinatorAgent(
        llm=llm, debate=debate, reflection=reflection, report=report
    )
    coordinator.register_agent("db", db_agent)
    coordinator.register_agent("server", server_agent)
    coordinator.register_agent("log", log_agent)

    return coordinator
```

### app.py 改动前后

改动前（`src/app.py:6-14` import + `:39-66` 函数与单例）：
```python
from src.core.llm import LLMClient
from src.core.coordinator import CoordinatorAgent
from src.agents.db_agent import DBAgent
from src.agents.server_agent import ServerAgent
from src.agents.log_agent import LogAgent
from src.agents.report_agent import ReportAgent
from src.core.debate import DebateArena
from src.core.reflection import ReflectionEngine
from src.config import load_config
# ...
def build_system():
    ...  # 26 行重复逻辑
coordinator = build_system()
```

改动后（`src/app.py:3-6` + `:31`）：
```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from src.core.bootstrap import build_system
# ...
coordinator = build_system()
```

### main.py 改动前后

改动前（`src/main.py:3-11` import + `:14-43` 函数）：
```python
from src.core.llm import LLMClient
from src.core.coordinator import CoordinatorAgent
from src.agents.db_agent import DBAgent
from src.agents.server_agent import ServerAgent
from src.agents.log_agent import LogAgent
from src.agents.report_agent import ReportAgent
from src.core.debate import DebateArena
from src.core.reflection import ReflectionEngine
from src.config import load_config

def build_system():
    ...  # 26 行重复逻辑
```

改动后（`src/main.py:3`）：
```python
from src.core.bootstrap import build_system


def main():
    coordinator = build_system()
    ...
```

---

## Test 层

### 验证命令与结果

1. bootstrap 构建验证：
```bash
python -c "from src.core.bootstrap import build_system; c = build_system(); print(type(c).__name__)"
# 输出：CoordinatorAgent
```

2. app.py 可导入验证：
```bash
python -c "import src.app; print('app import ok')"
# 输出：app import ok
```

两条命令均通过。`build_system()` 返回 `CoordinatorAgent`，`src.app` 模块级 `coordinator = build_system()` 在 import 阶段执行成功，说明装配链路完整、无 import 错误。

> 备注：运行时控制台打印了记忆系统加载日志（形如「Memory 已加载…历史记录」），因 GBK 控制台编码出现少量乱码，属日志噪声，非报错。

---

## Review 层（自查）

### 潜在问题
- **模块级单例副作用**：`app.py` 在 import 阶段即调用 `build_system()`，会读取配置并初始化 LLM 客户端。这是本次重构前已有的行为，未改变；若后续要做「延迟初始化 / 测试可替换」，需另开任务。
- **config.py 并行改造**：另一 agent 正改 config 的环境变量读取。本次仅依赖 `load_config()` 的签名与返回结构（`config["llm"]` 含 api_key/base_url/model），未触碰 config.py，两边解耦，无冲突。
- **无用 import 清理彻底性**：`app.py`/`main.py` 删除 build_system 后，原先仅供其使用的 9 个 import 全部移除；`app.py` 仅保留 FastAPI/HTTPException、BaseModel、bootstrap；`CoordinatorAgent` 在 app.py 中未作类型标注使用，故一并移除。

### 结论
重构达成目标：装配逻辑单点化，两个入口行为与重构前完全一致，验证通过。符合项目规范（中文注释、类型标注、单一职责、无裸 except）。
