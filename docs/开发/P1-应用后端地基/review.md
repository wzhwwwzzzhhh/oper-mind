# P1 独立审查 — 应用后端地基

> 更新时间：2026-07-26　|　结论：P1.1a 已提交；P1.1b 已提交

## P1.1a 复核

- 已提交：`1559266 chore: 恢复P1环境基线`。
- 根 `.venv`、锁定依赖、mock 健康检查、API smoke 与 pipeline smoke 的实际结论已记录。
- `.venv/`、本地配置、运行时数据、`frontend/`、`report/` 未进入该提交。

## P1.1b 审查范围

审查路径/配置集中实现、跨目录启动、环境变量优先级、敏感配置、旧 API 兼容、脚本/测试路径漂移与暂存边界。

| 检查项 | 结论 | 依据 |
|---|---|---|
| 资源路径唯一来源 | 通过 | `backend/src/project_paths.py` 统一提供根目录常量；配置、长期记忆、脚本与测试不再把 `backend/` 当作资源根 |
| 跨目录启动 | 通过 | 从仓库根、`backend/` 与临时目录的路径测试、评测校验和 smoke pipeline 均真实通过 |
| 配置优先级 | 通过 | `config.local.yaml` 优先模板，`OPERMIND_*` 环境变量覆盖；新增/既有配置测试共 8 项通过 |
| mock fallback | 通过 | 显式 mock 配置下 `/health` 返回 `200`、`mode=mock`；未写入密钥 |
| 阶段一 API 兼容 | 通过 | `backend/tests/test_api.py` 为 `11 passed`；未修改 `/diagnose`、`/diagnose/stream` 路由或契约 |
| 业务回归 | 通过 | 完整 `backend/tests` 为 `87 passed`；pipeline 四条覆盖路径通过 |
| 脚本路径漂移 | 通过 | `run_eval.py --help`、根评测校验、smoke pipeline 可由临时目录执行；无 `backend/data`、`backend/config`、`backend/experiments` 资源假设 |
| 敏感资产与范围 | 通过 | 不暂存 `.venv/`、`config/config.local.yaml`、运行时数据、实验产物、`frontend/`、`report/`；未引入 ORM、Migration、新路由或 React |

## 已知限制与风险

- `data/eval/validate.py` 作为根目录脚本仍需要一段最小启动桥接，原因是直接执行时 Python 仅把脚本目录放入 `sys.path`；业务资源定位仍集中在 `src.project_paths`，该桥接不读取当前工作目录。
- `TestClient` 仍报告既有 Starlette/httpx 弃用警告；本 Step 不升级依赖，已在 P1.1a 与本次回归中如实记录。
- 长期记忆的现有 `print` 输出和文件存储实现属于阶段一遗留，不在本 Step 清理；本次只修正默认资源路径。

## 结论

P1.1b 已达到成功标准并完成独立提交。提交信息：`refactor: 收口P1配置与数据路径`。提交后唯一下一步为 **P1.1c：应用后端地基设计**。
