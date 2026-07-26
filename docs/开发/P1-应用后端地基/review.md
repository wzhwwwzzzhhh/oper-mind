# P1 Review — P1.1a 环境基线恢复

> 日期：2026-07-26　|　审查范围：环境恢复、验证记录与当前入口同步　|　结论：通过，待用户授权提交

## 审查范围

- 根 `.venv` 的解释器、依赖安装与 Git 忽略边界
- `backend/requirements.txt` 的锁定依赖恢复
- mock 模式导入、健康检查、`backend/tests/test_api.py` 与 `backend/scripts/smoke_pipeline.py`
- `docs/开发/P1-应用后端地基/` 的设计、Step 与 HANDOFF
- A-Plan、阶段二计划、AGENTS/CLAUDE 与 P0.4 验证事实更正

## 检查项

| 检查项 | 结果 | 结论 |
|---|---|---|
| 分支边界 | 通过 | 已从 P0 分支创建 `feat/p1-application-foundation`，符合阶段二 `feat/pN-*` 规则 |
| 解释器基线 | 通过 | 发现 Python 3.10.11 与 3.11.9；根 `.venv` 固定为可用的 Python 3.11.9 |
| 旧环境根因 | 通过 | 旧 `.venv/pyvenv.cfg` 的创建命令仍指向废弃 `newproject` 路径，失效原因已精确记录 |
| 依赖恢复 | 通过 | `backend/requirements.txt` 安装完成，`pip check` 返回 `No broken requirements found.` |
| mock 导入与健康检查 | 通过 | 依赖导入成功，`config_mode=mock`、根 `data` 导入成功，`GET /health` 返回 200 / mock |
| API smoke | 通过 | `backend/tests/test_api.py` 为 11 passed；仅有既有 Starlette/httpx 弃用警告 |
| pipeline smoke | 通过 | direct / chain / parallel 与 debate 分支全部通过 |
| Git 与敏感资产 | 通过 | `.venv/`、`config/config.local.yaml` 被忽略，`data/memory.json` 无 diff；未把环境资产纳入提交范围 |
| 业务范围 | 通过 | 未修改 `backend/` 业务代码、数据库、ORM、Migration、Repository、API 行为、`frontend/` 或 `report/` |
| 文档准确性 | 通过 | P0.4 的 HTML 检查记录已更正为“提取内嵌脚本后运行 node --check”，不再声称 Node 直接检查 HTML |
| 计划入口 | 通过 | A-Plan、阶段二计划和 AGENTS/CLAUDE 统一指向 P1.1a；P1.1b 被明确为提交后的唯一下一步 |

## 已知限制

- `backend/src/config.py` 仍从 `backend/config/` 搜索 YAML，而模板在根 `config/`；本 Step 通过 mock 环境变量验证，不修改实现。
- 运行仍依赖 `PYTHONPATH="$PWD\backend;$PWD"` 同时解析 `backend/src` 与根 `data/`；这是 P1.1b 的唯一代码治理目标。
- API smoke 的 Starlette/httpx 弃用警告已记录，不阻塞本 Step；不在环境恢复中升级或替换依赖。

## 结论

P1.1a 达到可重复、可验证环境基线的成功标准。建议提交内容：`chore: 恢复P1环境基线`。提交后唯一下一步为 P1.1b 配置/数据路径收口；不得在该前置问题未解决前直接进入 ORM、Migration 或 `/api/v1` 实现。