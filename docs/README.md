# OperMind 文档入口

> **先读 `docs/开发/README.md`。** 项目总进度与唯一下一步以 `docs/开发/_A-Plan-总览.md` 为准。

## 读者路径

| 目的 | 阅读顺序 | 说明 |
|---|---|---|
| 继续当前工作 | `_A-Plan-总览.md` → `开发/README.md` → 当前工作包 `HANDOFF.md`（如有） | 只从 A-Plan 取得项目级下一步。 |
| 理解当前产品 | `开发/治理-DevOps-Copilot-MVP重定位/README.md`、`design.md` | 当前目标是受控靶场中的 DevOps Copilot 闭环。 |
| 理解范围与既有契约 | `_B-V1产品化开发计划.md`、`开发/P0-V1产品化基线/api-v1-contract.md` | B-Plan 定义工作包；P0 契约是已发布技术事实。 |
| 理解 Work 1 实现 | `开发/P4-DevOps-Copilot-MVP/`、`demo/orders-slow-query/README.md` | 真实靶场只限用户授权的 `opermind_demo`，不涉及 `gongkar`。 |
| 追溯研发与毕设材料 | `开发/M*/`、`report/`、`experiments/` | 用于 Trace、评测、实验和代码追溯，不定义当前产品下一步。 |

## 文档治理原则

1. **进度层**：只有 `_A-Plan-总览.md` 能声明项目状态、执行顺序和“当前唯一下一步”。
2. **产品层**：`治理-DevOps-Copilot-MVP重定位/` 定义当前产品方向和 P4.0 设计；B-Plan 展开工作包范围。
3. **规则层**：`docs/开发规范.md` 定义代码、安全、工作包、交接和文档规则。
4. **历史层**：封存材料保留技术事实，不能反向定义当前产品需求。

## 维护提醒

- 定位或路线调整先更新 A-Plan 和当前治理目录，再同步 B-Plan、规则镜像和索引；不要在多个文件维护“下一步”。
- 未实现能力必须显示空状态或明确 mock/靶场标识，禁止用假监控、告警或执行结果填补页面。
- 凭证、真实连接信息和本地运行时产物不得进入文档或 Git。