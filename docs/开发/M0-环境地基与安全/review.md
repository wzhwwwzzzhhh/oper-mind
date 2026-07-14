# M0 — 环境地基与安全（里程碑 Review）

> 里程碑：M0　|　分支：`feat/m0-foundation`　|　日期：2026-07-14
> 关联：`design.md`　|　步骤：step1〜step4

---

本文件是 M0 的**里程碑级审查**（双层审查的第二层）。各步骤的自审记录在各自的 `stepN-*.md` 末尾 Review 节，此处只做汇总核验 + 跨步骤一致性检查。

## 1. 验收标准核对（对照 design.md §6）

| 验收项 | 结果 | 证据 |
|---|---|---|
| 全历史无 `config.local.yaml`、无真实 key | ✅ | `git log --all -- config/config.local.yaml` 无输出；`sk-0218` 仅剩文档截断引用 |
| `config.py` 支持 env 覆盖，mock 不受影响 | ✅ | step2 四项测试 PASS；env 缺失时 fallback YAML |
| `app.py`/`main.py` 无重复 `build_system()`，import 自 bootstrap | ✅ | 两文件均 `from src.core.bootstrap import build_system` |
| `requirements.txt` 补全 | ✅ | 补 pyyaml、fpdf；sqlalchemy/pymysql 注释占位（M6） |
| 三路径 mock 冒烟测试通过 | ✅ | `scripts/smoke_pipeline.py` 退出码 0，direct/chain/parallel 全通 |
| 审查通过并记录 | ✅ | 本文件 |

## 2. 代码审查

- **bootstrap.py**：类型标注齐全（`-> CoordinatorAgent`），中文注释，无裸 except，装配逻辑单一可信。符合硬约束。
- **config.py**：env 优先 / YAML fallback，`load_config()` 签名与返回结构 `{"llm": {...}}` 未变，向后兼容；仅当拿不到 api_key 时抛 `FileNotFoundError`。
- **app.py / main.py**：重复的 `build_system()` 已消除，两入口收敛到单一来源。
- **smoke_pipeline.py**：修复 Windows GBK 控制台无法编码 emoji 的问题（顶部重配 stdout/stderr 为 UTF-8），非 pipeline 逻辑问题。

## 3. 冒烟测试结论

三条路由链路均验证通过：
- chain：`route → chain → chain → chain → report → reflection`
- parallel（无冲突）：`route → parallel → conflict_check → report → reflection`
- parallel（有冲突 → 辩论）：`route → parallel → conflict_check → debate → report → reflection`

每条链路都经过 `report` + `reflection` 质量保障节点。

## 4. 遗留项 / 风险

| 项 | 归属 | 说明 |
|---|---|---|
| 吊销旧 DeepSeek key | **用户** | 代码侧无法代劳，务必在控制台确认已吊销并换新 |
| `sk-0218...` 文档引用 | 已决策保留 | 截断前缀，标记被吊销的 key，不构成泄露 |
| filter-branch 与远程 | 未来 | 现无远程仓库；若推远程需协作者重新 clone |
| CLAUDE.md 目录结构漂移 | 后续里程碑 | report_agent 非真 Agent、frontend 空、config.py 位置等与实际有出入，重构时同步订正 |

## 5. 结论

**M0 通过**。地基隐患（密钥、配置、依赖、重复）已清理，三路径 pipeline 在 mock 模式下可复现跑通，可进入 M1。
