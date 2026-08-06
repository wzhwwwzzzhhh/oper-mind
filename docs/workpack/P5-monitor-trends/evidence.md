# P5-monitor-trends · AC 证据

## 测试证据

- 后端全量：`114 passed`。
- P5 后端聚焦：`21 passed`，包括采样器、历史查询、schema 和持久化迁移回归。
- 干净 SQLite migration：`upgrade head`、`downgrade 20260802_04_p2_tool_invoked`、再次 `upgrade head` 全部通过。
- 前端 `npm run typecheck`：通过。
- 前端服务详情聚焦测试：`18 passed`。
- 前端全量测试：`9 files / 55 tests passed`。
- 前端构建：通过；仅有既有约 903 kB bundle size warning。
- OpenAPI：`npm run generate:api` 已执行并生成历史查询接口类型。
- P5 文件范围 `git diff --check`：通过。
- 独立审查：tooling blocked，未产生独立 PASS。

## AC 状态

| AC | 状态 | 证据 |
|---|---|---|
| AC1 | PASS | 定时采样、样本表、升序历史查询测试 |
| AC2 | PASS | 未配置样本 null 标量测试 |
| AC3 | PASS | 失败隔离与 3 秒异步超时实现 |
| AC4 | PASS | 历史窗口查询应用测试与脱敏 schema |
| AC5 | PASS | 前端无样本诚实空态 |
| AC6 | PASS | 异常点高亮和摘要前端测试 |
| AC7 | PASS | 历史来源/频率/保留窗口文案 |
| AC8 | PASS | 后端全量回归和前端既有测试 |
| AC9 | PASS | 领域模型与响应字段白名单 |

## 未决门禁

- 独立审查工具当前不可用，暂不能完成最终 Review PASS。
- 当前分支含其他工作包共享文件改动，commit 前必须检查 staged diff，不能使用 `git add .`。
