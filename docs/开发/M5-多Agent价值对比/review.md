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

---

## Step3 Review — 区分度用例集

> 审查日期：2026-07-20　|　审查方式：**派 code-review 子 agent 独立审**（动 schema/runner，非平凡）+ validate/全量回归

### 对 step2 结论的纠正

step2 结论把「全局状态并发切换」列为 step3 前置项——复核后确认 **over-flag**：Runner 逐条**串行**跑用例，单条内 parallel 三 agent 只读已设场景，无用例间串扰，全局对串行 Runner 安全。contextvar 仅在并行跑用例 / 并发 API 时才需要（YAGNI），本步不做、仅文档标注边界。

### 发现与处置（审查无 ≥80 阻断项，均为可选建议）

| # | 严重度 | 发现 | 处置 |
|---|---|---|---|
| 1 | 低 | mislead-004 的 `expected_agents` 顺序与其余不一致 | ✅ 已统一为 `["server","db","log"]` |
| 2 | 低 | test 文件中部 import | ✅ 已提到文件顶部 |
| 3 | 低 | schema 可用 `Literal` 在构造期收紧 scenario 取值 | ⏭ 不改：会使 schema 与 scenarios 的 key 两处需同步；现 str + validate 更解耦（决策） |
| 4 | 低 | runner 非法 scenario 在 try 外 → 会中断整套 | ⏭ 不改：**有意 fail-fast**——非法 scenario 属数据错误、validate 已前置拦截，比"用残留场景静默跑错"更安全（决策） |

### 核对结论（审查逐项确认）

- 12 条 golden 与 `data/scenarios.py` 的 S2/S3/S4 数据**逐条一致、可核对**；表象误导型 golden 均指向"非表象"根因。
- `expects_debate=true` 仅出现在 parallel；6 条 mislead-* 稳妥命中 chain、6 条 conflict-* 稳妥命中 parallel（parallel 优先级最高，含"慢/超时"也不误路由）。
- 类型标注齐全、无裸 except、中文注释、mock 确定性。

### 验收

- validate 77 条全过、全量 68 passed、smoke 退出码 0。

- **结论：通过。**

---

## Step4 Review — 对比实验与指标（token / 切片）

> 审查日期：2026-07-20　|　审查方式：**派 code-review 子 agent 独立审**（动 llm/runner/schema，非平凡）+ 全量回归

### 核对结论（审查逐项确认，无 ≥80 阻断项）

- **token 分离正确**：全系统共用同一 `llm` 实例（`bootstrap.py`），`coordinator.llm.total_tokens` 覆盖 direct/chain/parallel 全链路诊断调用；快照差取在 route 后、judge 前 → 只含诊断 token，不含裁判（真实模式裁判是独立实例，mock 下裁判不累加，双重保证）。
- **mock=0 成立**：mock 路径在累加逻辑前 return，`mean_tokens` 恒 0。
- **切片正确**：by_scenario/by_case_group 复用同一 `_stats`，与 by_domain 口径一致；`_case_group` 前缀归类无误伤。
- **compare_arms 健壮**：无参/缺目录/缺 meta/新旧混用均安全。
- **规范/兼容**：类型标注齐、无裸 except、旧结果缺 tokens 字段默认 0 不崩。

### 发现与处置（均为低置信可选项）

| # | 发现 | 处置 |
|---|---|---|
| 1 | compare_arms 的 `json.load` 未覆盖"文件损坏"场景 | ✅ 已加 `JSONDecodeError` 兜底 |
| 2 | `_case_group` 用 `run_result["case_id"]` 而非 `case.case_id` | ✅ 已统一为 `case.case_id` |
| 3 | `llm.py:64` `print` 生产日志违反 CLAUDE.md | ⏭ 既有技术债、非本次改动范围，不在此 commit 扩范围处理 |

### 验收

- 全量 72 passed；mock run_eval + compare_arms 全跑通、切片正确落盘。

- **结论：通过（代码层面）。真实跑批的质量结论待用户执行 Phase A 后产出。**
