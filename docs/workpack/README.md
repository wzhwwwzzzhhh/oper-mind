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

| 阶段 | 切片 | plan.md | review | evidence | 状态 |
|---|---|---|---|---|---|
| P4.2 | db-agent-real | ✅ 待审阅 | — | — | 待用户确认 |
| P4.3 | model-settings-real | ✅ | ✅ PASS | ✅ | 已实现待交付 |
| P4.4 | service-instances | ✅ 待审阅 | — | — | 待用户确认 |

## 已归档

| 阶段 | 切片 | PR | 完成日期 |
|---|---|---|---|
| （暂无） | | | |

## 规则
- `plan.md` 必须经用户确认后才进入 `dev-execute`；`review.md` 必须 PASS 才能进入 `dev-deliver`。
- 归档后 `docs/workpack/归档/` 内文件只读，不再修改。
