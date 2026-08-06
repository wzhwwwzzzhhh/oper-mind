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
| P5 | monitor-trends | 待用户确认计划 | [plan](P5-monitor-trends/plan.md) | 待执行 | 待执行 |
| P5 | controlled-action-real | 已实现，待交付 | [plan](P5-controlled-action-real/plan.md) | [review](P5-controlled-action-real/review.md) | [evidence](P5-controlled-action-real/evidence.md) |
| P6 | redis-service-monitor | 待 Review | [plan](P6-redis-service-monitor/plan.md) | [review](P6-redis-service-monitor/review.md) | [evidence](P6-redis-service-monitor/evidence.md) |

## 已归档

| 阶段 | 切片 | PR | 完成日期 |
|---|---|---|---|
| P4.2 | db-agent-real | #1 | 2026-08-05 |
| P4.3 | model-settings-real | #2 | 2026-08-05 |
| P4.4 | service-instances | — | 2026-08-05 |

## 规则
- `plan.md` 必须经用户确认后才进入 `dev-execute`；`review.md` 必须 PASS 才能进入 `dev-deliver`。
- 归档后 `docs/workpack/归档/` 内文件只读，不再修改。
