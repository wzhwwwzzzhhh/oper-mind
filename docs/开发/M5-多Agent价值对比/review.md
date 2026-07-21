# M5 Review — 多 Agent 价值对比

> 逐 step 审查记录（每步审、不后置）。里程碑末尾在此汇总。

---

## Step1 Review — 评测口径修复

> 审查日期：2026-07-20　|　审查方式：主持人自查 + 全量回归

- 改动小且聚焦（stub 词元级重合），真实裁判路径未动。
- 现有 mock 用例行为不变（关键点为单词元时等价），新增 2 条覆盖新行为。
- 验收：test_judge 13 passed、全量 57 passed、smoke 退出码 0。
- **结论：通过。**

---

## Step2 Review — 多故障 mock 世界

> 审查日期：2026-07-20　|　审查方式：**派 code-review 子 agent 独立审**（动架构 + 删文件，属非平凡改动）+ 全量回归

### 发现与处置

| # | 严重度 | 发现 | 处置 |
|---|---|---|---|
| 1 | 重要 | 模块级全局 `_active_scenario` 会被 `build_system(mock)` 置为 S1，可能污染后续依赖 psutil 的用例；且 step3 并行按用例切场景时进程级全局有并发隐患 | ✅ 新增 `tests/conftest.py` autouse 夹具，每例后 `clear_active_scenario`，修测试污染；⏭ 并发问题记为 **step3 前置项**（改 contextvar 或传参，勿用进程级全局做并行切换） |
| 2 | 重要 | 真实模式下 server 走 psutil、log/db 仍走 S1，两者可能不一致 | 📝 记为已知限制（见 step2.md）：真实模式是过渡态，M8 真 MySQL 前 log/db 无真实源；不影响 mock 主实验 |
| 3 | 次要 | frozen dataclass 持可变 dict，若被原地改会污染共享单例 | ✅ 字段加「只读，勿原地改」注释；当前全部只读 |
| 4 | 次要 | `server_tools.py` 未使用的 `import json`（历史遗留） | ✅ 顺手删除 |

### 验收

- test_scenarios 9 passed、全量回归通过、smoke 退出码 0。
- 无阻断项；重要项均已处置或明确转 step3。

- **结论：通过**（step3 须先解决全局状态的并发切换，再做按用例切场景）。
