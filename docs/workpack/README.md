# 工作包索引（docs/workpack/）

> 本目录是**开发执行产物**：按工作包记录「计划 → 审查 → 证据」，与 `docs/prd/`（需求唯一事实来源）隔离。
> 执行流程见 `.claude/skills/dev-plan`、`dev-execute`、`dev-deliver`。

## 目录约定

```
docs/workpack/
  <阶段>-<切片 kebab>/        # 每个切片一个工作包，如 P4.2-db-agent-read-slice
    plan.md                   # 实现计划（dev-plan 产出，需用户确认）
    review.md                 # 子代理独立审查结论（dev-execute 产出）
    evidence.md               # AC 证据表（dev-execute 逐步回写）
  归档/                        # 已交付并关闭的切片（只读，不删）
    <阶段>-<切片 kebab>/
  README.md                   # 本索引
```

## 活跃工作包

| 阶段 | 切片 | 状态 | 计划 | Review | 证据 |
|---|---|---|---|---|---|
| P8 | service-registration | 待用户确认计划 | [plan.md](P8-service-registration/plan.md) | — | — |

## 已归档

| 阶段 | 切片 | PR | 完成日期 |
|---|---|---|---|
| P8 | workbench-loop-closure | #57 | 2026-08-10 |
| P8 | model-mode-switch | #56 | 2026-08-10 |
| P4.2 | db-agent-real | #1 | 2026-08-05 |
| P4.3 | model-settings-real | #2 | 2026-08-05 |
| P4.3 | service-context | #19 | 2026-08-06 |
| P4.4 | service-instances | — | 2026-08-05 |
| P6 | redis-service-monitor | #18 | 2026-08-06 |
| P6 | knowledge-retrieval | #24 | 2026-08-06 |
| P6 | model-provider-key-management | #32 | 2026-08-07 |
| P6 | log-source-real | #29 | 2026-08-08 |
| P6 | host-metrics | #34 | 2026-08-08 |
| P5 | controlled-action-real | #38 | 2026-08-08 |
| P5 | monitor-trends | #13 | 2026-08-08 |
| P6 | cross-service-investigation | 待建 PR | 2026-08-08 |
| P7 | db-lock-connection-diagnostics | #46 | 2026-08-08 |
| P7 | knowledge-page | #48 | 2026-08-08 |
| P7 | monitoring-overview | #50 | 2026-08-08 |

## 规则
- `plan.md` 必须经用户确认后才进入 `dev-execute`；`review.md` 必须 PASS 才能进入 `dev-deliver`。
- 归档后 `docs/workpack/归档/` 内文件只读，不再修改。
