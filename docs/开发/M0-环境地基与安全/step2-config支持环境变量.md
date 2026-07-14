# M0 · Step2 — config 支持环境变量覆盖

## Design 层

### 为什么改
安全整改。原先 `load_config()` 只从 `config/config.local.yaml`（本地，含真实 key）和 `config/config.example.yaml`（模板）读取配置。真实密钥落在本地 yaml 文件里，一旦误提交或本地泄露就有风险。该 local yaml 已从 git 移除，因此需要一条不依赖本地文件的密钥注入通道。

### 方案
采用「yaml 打底 + 环境变量覆盖」的分层配置：

1. 先从 yaml 读到基础配置（`local` 优先，`example` 兜底，都没有则视为空配置）。
2. 再用环境变量覆盖 `llm` 段的字段——环境变量存在即优先，缺失则保留 yaml 原值。

环境变量约定：

| 环境变量 | 覆盖字段 |
|---|---|
| `OPERMIND_API_KEY` | `llm.api_key` |
| `OPERMIND_BASE_URL` | `llm.base_url` |
| `OPERMIND_MODEL` | `llm.model` |

### 取舍
- **函数签名与返回结构不变**（`load_config() -> dict`，结构仍是 `{"llm": {...}}`），调用方 `app.py`/`main.py` 零改动。这是硬约束，避免改造外溢。
- **报错时机后移**：不再「yaml 缺失就抛错」，改为「拿不到 `api_key` 才抛错」。这样纯环境变量（无任何 yaml）也能跑起来，是本次改造的核心目的。
- **保留 mock 模式**：`OPERMIND_API_KEY=mock` 作为一等公民，用于开发、测试与答辩演示；改造对它天然透明——mock 只是 api_key 的一个取值。
- **拆分私有函数**：把 yaml 加载与 env 覆盖拆成 `_load_yaml_config()` 与 `_apply_env_overrides()`，单一职责，便于测试与阅读。

## Step 层

1. 定义环境变量到 llm 字段的映射常量 `_ENV_TO_LLM_KEY`。
2. 抽出 `_load_yaml_config()`：只负责按优先级找 yaml 并返回 dict，找不到返回空 dict（不再抛错）。
3. 新增 `_apply_env_overrides()`：用 `setdefault("llm", {})` 保证挂载点存在，再逐个用存在的环境变量覆盖。
4. 重写 `load_config()`：串起「yaml 打底 → env 覆盖 → 校验 api_key」，仅在拿不到 api_key 时抛 `FileNotFoundError`（错误信息补充环境变量用法）。
5. 更新 `config/config.example.yaml`，加注释推荐用环境变量、告诫勿把真实 key 写进 yaml。
6. 写临时脚本验证三/四个场景，通过后删除。

## Code 层

环境变量映射常量（`src/config.py:9`）：

```python
_ENV_TO_LLM_KEY = {
    "OPERMIND_API_KEY": "api_key",
    "OPERMIND_BASE_URL": "base_url",
    "OPERMIND_MODEL": "model",
}
```

yaml 缺失时返回空 dict 而非抛错（`src/config.py:35`）：

```python
for path in candidate_paths:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            # 空文件时 safe_load 返回 None，统一成空 dict
            return yaml.safe_load(f) or {}
return {}
```

环境变量覆盖，缺失则保留 yaml 原值（`src/config.py:52`）：

```python
llm_config = config.setdefault("llm", {})
for env_name, llm_key in _ENV_TO_LLM_KEY.items():
    env_value = os.environ.get(env_name)
    if env_value is not None:
        llm_config[llm_key] = env_value
```

延后到「拿不到 api_key 才报错」（`src/config.py:77`）：

```python
if not config.get("llm", {}).get("api_key"):
    ...
    raise FileNotFoundError(...)  # 信息中补充环境变量用法
```

## Test 层

用临时脚本（跑完已删）通过 monkeypatch 环境变量与临时切换 yaml 目录，覆盖以下场景：

| 场景 | 设置 | 期望 | 结果 |
|---|---|---|---|
| a. mock 模式 | `OPERMIND_API_KEY=mock` | `api_key == "mock"` | PASS |
| b. env 覆盖 yaml | yaml 有值 + 三个环境变量都设 | 三字段均为 env 值（`sk-env-override` / `https://env.example.com` / `env-model`） | PASS |
| c. 无 yaml 仅 env | 临时指向无 yaml 目录 + `OPERMIND_API_KEY=mock` | 正常返回，`api_key == "mock"` | PASS |
| d. 无 yaml 且无 env（补充负例） | 无 yaml + 清空环境变量 | 抛 `FileNotFoundError` | PASS |

实际运行输出（末行）：`ALL PASS`。

## Review 层（自查）

- **环境变量为空字符串**：用 `os.environ.get(...) is not None` 判断，因此 `OPERMIND_API_KEY=""`（显式设空）会覆盖 yaml 且随后校验 `if not api_key` 触发报错——符合预期（空 key 视为未配置）。若未来希望「空串=不覆盖」，需改判断条件，目前语义清晰无隐患。
- **example.yaml 兜底的占位 key**：`config.example.yaml` 里有占位 `api_key`，意味着即便没设环境变量、也没 local 文件，`load_config()` 仍会返回占位值而不报错。这沿袭了原有行为（原代码也会返回 example 内容），非本次回归；真实运行时占位 key 会在 LLM 调用处失败，属可接受的既有行为。
- **返回结构兼容**：仅覆盖/新增 `llm` 段字段，未动其它键，调用方 `config["llm"]["api_key"]` 等访问方式不受影响。
- **未用裸 except**：全程无 try/except，异常路径只有显式 `raise`。
- **结论**：满足全部要求（签名/结构不变、env 覆盖、缺 yaml 靠 env 可跑、mock 保留、中文注释与类型标注、单一职责），验证通过。
