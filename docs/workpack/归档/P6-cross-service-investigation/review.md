# P6-cross-service-investigation · 独立审查

> 审查方式：只读子代理，核对 PRD、已确认 Design、计划和工作区差异。

## 结论

**PASS**（无未处理的 P0/P1）。

## 审查发现与处理

1. `session_services` 的约束未覆盖已注册的 `redis-production`，会使 Redis 联合调查在数据库提交时失败。
   → 已将 Redis 纳入领域白名单和迁移 CHECK 约束，并新增 Redis 持久化与迁移保护测试。
2. 多 Run 顺序提交在一个服务请求失败后停止，且可能丢失已受理 Run 的恢复状态。
   → 已改为逐个提交未受理 Run、保留各自幂等键和已受理状态；失败服务只显示独立提示，重试不会重复提交已受理服务。
3. 连续同问题的聚合条件过宽，可能合并重复单服务或无服务问题。
   → 仅在相邻、时间相近且服务标识不同的调查之间聚合；新增不合并回归测试。
4. 前端公开类型初始未生成。
   → 由本地 `src.app:app` 的 OpenAPI 正式重新生成 `generated.ts`，移除临时类型扩展。

## 验证结论

- 后端聚焦回归：`41 passed`。
- 后端全量回归：`267 passed, 2 skipped`。
- 迁移：upgrade → downgrade -1 → upgrade 通过；关联数据存在时 downgrade 被安全拒绝。
- 前端：`typecheck`、`72 passed`、生产 `build` 全部通过。
- `git diff --check` 通过。前端测试有 jsdom pseudo-element 的既有提示，构建有既有大 chunk 提示，均未导致失败。

## 遗留事项

- 无功能或安全阻塞项。
