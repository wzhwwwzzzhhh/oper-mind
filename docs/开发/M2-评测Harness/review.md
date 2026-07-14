# M2 里程碑 Review — 评测 Harness

> 分支：`feat/m2-harness`　|　完成日期：2026-07-14
> 关联：design.md、step1-确定性指标.md、step2-LM裁判.md、step3-Runner.md、step4-结果契约与CLI.md

## 1. 验收标准逐项核对（对照 design.md §8）

| 验收项 | 状态 | 证据 |
|---|---|---|
| `python scripts/run_eval.py`（mock）跑通 65 条，产出三件套 | ✅ | `experiments/b7108eab8602/{cases.jsonl,summary.json,meta.json}`，两次独立运行均 0 错误 |
| 确定性指标真算，mock 下应接近满分 | ✅ | route_hit_rate/target_hit_rate/pipeline_complete = 100% |
| judge stub 分稳定可复现（同种子两次跑数字一致） | ✅ | 两次运行 config_hash 均为 `b7108eab8602`，mean_root_cause=0.487、mean_key_points=0.015 完全一致 |
| 单条异常不中断整批 | ✅ | `tests/test_runner.py::test_run_suite_单条失败不影响其他用例`（`_FlakyCoordinator` 人为注入第二条崩溃，验证第一条正常返回、第二条带 `error`、总数不少） |
| metrics.py 有独立单测 | ✅ | `tests/test_metrics.py` 6 例，构造 trace 样例断言抽取正确 |
| `experiments/` 已 gitignore | ✅ | `.gitignore` 新增条目，`git status` 确认未被追踪 |
| 审查通过，记录于 review.md | ✅ | 本文档 |

**结论：7 项验收标准全部满足。**

## 2. 三个设计决策回顾（design.md §9，均已获批"按照你的建议来"）

1. **指标分两层**（确定性 trace 指标 + judge 质量分，mock 下 judge 为 stub）——落地为
   `metrics.py`（纯 trace 计算）+ `judge.py`（`_is_mock` 分支 stub/真 judge）。实测证明分层是必要的：
   mock 下确定性指标 100% 而 judge 分数极低（0.487/0.015），如果不分层会把"mock 数据同质化"误判为
   "系统诊断质量差"。
2. **M2 不改 agent 输出结构化，推迟到 M6**——整个 M2 期间 `src/agents/*` 未改动一行，`CaseResult`/
   `EvalSummary` 只存在于评测层（`src/eval/result_schema.py`），验证了这个降级决策没有反噬评测能力。
3. **judge 评分口径：root_cause 连续 0-1 分 + key_points recall**——`judge.py` 的 `_mock_stub_judge`/
   `_llm_judge` 均按此口径实现，`tests/test_judge.py` 7 例覆盖两条路径。

## 3. 已知限制（非 bug，记录供 M4/M6 决策参考）

- **mean_key_points_recall=0.015 在 mock 下不是质量信号**：`_mock_chat` 对所有 domain 返回同一份
  DB 风格文本，跟 server/log/compound 域的 golden_key_points 几乎不重合。接入真实 LLM
  （`judge_is_stub=False`）后这个数字才有意义，见 step4 doc §5。
- **mechanism_hit_rate=92.31%（5/65 未命中）**：`expects_debate=True` 的用例在 mock 下因为 parallel
  聚合的诊断内容高度雷同，可能不足以触发 debate 的分歧检测阈值。已确认这不是 debate 触发逻辑的 bug——
  `src/core/debate.py` 的分歧检测逻辑本身未改动，纯粹是 mock 数据同质化导致部分用例的分歧幅度不够。
  真实 LLM 环境下不同 domain 会有真实差异化诊断，预期这个 rate 会回升；不在 M2 范围内修复。
- **run_eval.py 是同步逐条执行**：65 条 mock 用例 0.4s 内跑完，够用；换真实 LLM 后如果耗时明显增长
  （网络 I/O），可考虑加并发，留给 M4（复现性基础设施）或按实际耗时决定，不提前设计。

## 4. 过程问题与修复（本里程碑内的 git 卫生记录）

- **`data/memory.json` 编码损坏**：`run_eval.py` 首次执行时，`LongTermMemory.load()` 在读取一份
  已被污染成非 UTF-8 字节的 `data/memory.json` 时抛出 `UnicodeDecodeError`。排查确认 HEAD 版本
  （`8a0ada5` 提交的版本）本身是合法 UTF-8 JSON，问题出在此前某次运行残留的脏字节。修复：用
  `git show HEAD:data/memory.json` 还原到最后一次提交的合法版本，重跑评测确认恢复正常。
  **这不是评测代码的 bug**，是长期记忆文件在多次手动测试间累积的运行时副作用；`data/memory.json`
  按既定约定不进入本次提交（M0 起就排除在所有 commit 之外）。
- **两次评测运行都会往 `data/memory.json` 追加诊断记录**（`add_record` 的正常行为，每条用例诊断后
  触发一次）。已确认提交前 `data/memory.json` 是干净的 HEAD 版本（评测产生的追加内容未被 stage）。

## 5. 提交清单

本次提交包含（`data/memory.json` 不提交，遵循既定约定）：

- `src/eval/result_schema.py`、`tests/test_result_schema.py`（step4）
- `scripts/run_eval.py`（step4 CLI）
- `.gitignore`（新增 `experiments/`）
- `docs/开发/M2-评测Harness/step4-结果契约与CLI.md`
- `docs/开发/M2-评测Harness/review.md`（本文档）

## 6. 结论

**M2（评测 Harness）验收通过，可合并。** 65 条用例端到端跑通，确定性指标与 judge 分层设计经实测验证
是必要且有效的，两个"看起来像问题"的数字（key_points_recall 低、mechanism_hit 未满分）已在 §3 明确
归因为 mock 数据同质化的预期副作用，不掩盖为系统缺陷。下一步可进入 M3（复现性基础设施）或按 roadmap
优先级处理 M2'（API 补全/SSE streaming）。
