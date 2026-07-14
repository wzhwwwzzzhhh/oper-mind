# M0 — 环境地基与安全（Design 层）

> 里程碑：M0　|　分支：`feat/m0-foundation`　|　状态：进行中
> 创建日期：2026-07-14
> 关联路线图：`docs/开发路线图与规划.md` → M0

---

## 1. 要解决的问题

项目在进入正式功能开发前，存在一批「地基级」隐患，必须先清理，否则后续每个里程碑都会踩：

1. **密钥泄露**：`config/config.local.yaml` 内含真实 DeepSeek key，且已进 git 历史。
2. **配置不支持环境变量**：`config.py` 只读 YAML，key 无法从 env 注入，CI / 多环境 / 安全实践都受限。
3. **依赖不全**：`requirements.txt` 缺 `pyyaml`、`fpdf`（config.py 和脚本在用），`pip install -r` 装不全。
4. **代码重复**：`build_system()` 在 `app.py:39-64` 与 `main.py:14-43` 逐字重复，改一处易漏另一处。

## 2. 方案与取舍

### 2.1 安全（已完成）
- **吊销 key**：用户在 DeepSeek 控制台吊销 `sk-0218...` 并换新（只有用户能做）。
- **洗历史**：因未安装 `git-filter-repo` 且无 pip，改用 git 自带 `git filter-branch` 从全部 8 个 commit 删除 `config.local.yaml`。
  - 取舍：`filter-branch` 官方已不推荐（慢、易错），但本仓库只有 8 个 commit、无远程、目标文件单一，够用且免安装。
- **停跟踪**：`git rm --cached config/config.local.yaml`，配合已有的 `.gitignore` 规则生效。
- 洗历史前先提交 WIP 快照（`8813a05`）并把 `config.local.yaml` 备份到仓外，防误删本地配置。

### 2.2 config.py 支持环境变量
- **方案**：加载顺序改为「环境变量优先，YAML fallback」。`OPERMIND_API_KEY` / `OPERMIND_BASE_URL` / `OPERMIND_MODEL` 若存在则覆盖 YAML 对应字段。
- **取舍**：不引入 `python-dotenv` 等新依赖，直接读 `os.environ`，保持轻量。mock 模式（`api_key="mock"`）不受影响。
- 保留 YAML 作为本地开发便利，env 作为安全/CI 通道。

### 2.3 bootstrap.py 去重
- **方案**：新建 `src/core/bootstrap.py`，把 `build_system()` 抽进去；`app.py` 和 `main.py` 都 import。
- **取舍**：放 `src/core/` 而非 `src/`，因为它属于框架装配逻辑，与 core 内聚。

### 2.4 补依赖
- `requirements.txt` 补 `pyyaml`、`fpdf`；`sqlalchemy`、`pymysql` 作为 M6 真实 DB 的占位（注释标注「M6 用」）。

## 3. 影响的模块

| 文件 | 变更 |
|---|---|
| git 历史 | 删除 `config.local.yaml`（已完成） |
| `src/config.py` | 支持环境变量优先 |
| `src/core/bootstrap.py` | 新建，承载 `build_system()` |
| `src/app.py` | 删除本地 `build_system()`，改 import |
| `src/main.py` | 删除本地 `build_system()`，改 import |
| `requirements.txt` | 补依赖 |

## 4. 结构化契约变化

无。M0 是地基清理，不涉及 ToolResult / AgentDiagnosis 等契约（那是 M2）。

## 5. 步骤拆分

- `step1-洗历史.md`（已完成，补记录）
- `step2-config支持环境变量.md`
- `step3-bootstrap去重.md`
- `step4-补依赖.md`
- `review.md`（里程碑级审查报告，全部完成后汇总）

## 6. 验收标准

- [ ] 全历史无 `config.local.yaml`、无真实 key
- [ ] `config.py` 支持 env 覆盖，mock 模式不受影响
- [ ] `app.py` / `main.py` 无重复 `build_system()`，import 自 bootstrap
- [ ] `requirements.txt` 补全，`pip install -r` 可成功
- [ ] 三路径 mock 冒烟测试（`scripts/smoke_pipeline.py`）通过
- [ ] 审查通过，记录于 `review.md`
