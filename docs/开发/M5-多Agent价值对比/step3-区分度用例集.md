# M5 Step3 — 区分度用例集

> 状态：✅ 完成（2026-07-20，code-review 通过）
> 分支：`feat/m5-agent-comparison`

## 背景

要让「多 Agent vs 单模型」出现差距，必须有单模型会误判、多 Agent 交叉验证能纠偏的用例。本步接入 step2 的多故障世界，加 `scenario` 绑定 + 编写区分度用例。

## 决策（含对 step2 review 的纠正）

- **并发前置项 over-flag 纠正**：step2 review 把「进程级全局场景」列为 step3 必须先改 contextvar 的前置项。复核后：评测 Runner **逐条串行**跑用例，单条内 parallel 三 agent 只**读**已设好的场景，不存在用例间串扰 → 全局对串行 Runner **安全**。contextvar 仅在「并行跑用例 / 并发 API 服务不同场景」时才需要，属 YAGNI，本步不做，仅文档标注边界。
- `EvalCase` 加可选 `scenario: str = "S1"`：旧 65 条不写则仍 S1，行为不变。
- 约 12 条新用例，绑定 S2/S3/S4。

## Code 改动

- `data/eval/schema.py`：`EvalCase` 加 `scenario` 字段（默认 S1）。
- `data/eval/validate.py`：新增 `check_scenarios`（scenario 必须是注册 key）+ 分布打印加 scenario + main 纳入。
- `src/eval/runner.py`：`run_case` 在 `coordinator.route` 前 `set_active_scenario(case.scenario)`（串行安全，注释标注 contextvar 边界）。
- `data/eval/cases.jsonl`：追加 12 条——
  - **表象误导型 6 条**（`mislead-001..006`，chain，`expects_debate=false`）：S4 报连接错像 DB 慢（真因配置）、S2 写失败像应用 bug（真因磁盘满）、S3 内存高像需扩容（真因应用堆泄漏），含直接反驳「加索引」「加内存」错误假设的用例。
  - **真分歧型 6 条**（`conflict-001..006`，parallel，`expects_debate=true`）：三源归因不同，辩论收敛到真根因（S2 磁盘满 / S3 应用泄漏 / S4 连接配置）。
- golden 按场景写死、互不可换，单模型「猜恒定答案」会翻车。

## Test 证据

```text
python data/eval/validate.py   → 77 条全过；scenario 分布 S1=65/S2=4/S3=4/S4=4；
                                  chain=16、parallel=16、expects_debate=11；路由一致
python -m pytest -q             → 68 passed（step2 后 66，+2：schema 默认 + runner 切场景）
python scripts/smoke_pipeline.py→ 退出码 0
```

## 已知限制 / 交给 step4

- mock 模式下 agent 推理是模板 stub，**区分度只有在真实 LLM 跑批时才体现**（step4）。本步只保证结构、路由、场景切换正确。
- 每场景仅 4 条，规模够 step4 出对比信号、非论文级统计规模。
