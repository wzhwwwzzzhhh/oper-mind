# M1 · Review — 评测数据集建设

> 里程碑：M1　|　分支：`feat/m1-dataset`　|　审查日期：2026-07-14
> 审查人：主集成者（对四域 agent 产出做统一审查）

---

## 1. 验收对照（design.md 第 6 节）

| 验收标准 | 结果 |
|---|---|
| schema 用 Pydantic 定死契约，跨字段一致性校验 | ✅ `schema.py`，`model_post_init` 校验策略↔agent 数、debate 约束 |
| 校验器复用运行时路由函数（非复制逻辑） | ✅ `validate.py` 直接 import `graph._keyword_strategy/_keyword_target` |
| 50–100 条用例，四域 + 三策略覆盖 | ✅ 65 条：db18/server15/log12/compound20；direct45/chain10/parallel10 |
| 含跨领域复合故障 | ✅ compound 20 条，chain 逐层根因串 + parallel 多维/分歧 |
| 每条带 golden 标注 | ✅ golden_root_cause + golden_key_points（3–5 点） |
| 全量校验零错误、路由一致 | ✅ 65 条全绿 |
| 唯一可信源，无多源漂移 | ✅ 合并后删 4 分片 + 生成器脚本 |

## 2. 质量抽查（审查层，校验器覆盖不到的部分）

校验器只保证「格式合法 + 路由一致」，不保证 golden 标注本身合理。逐条抽查 compound 20 条（最高风险），结论：

**扎实项**：
- parallel 10 条全部锚定真实 mock 现象（全表扫描 / OOM Killer / 连接池耗尽 / mysqld CPU 85%）。
- 5 条 debate 用例（parallel-004/005/008/009/010）分歧构造合理：server 归因资源、db 归因慢查询、log 归因连接耗尽，辩论收敛到「DB 慢查询为源头」，符合 debate 节点的启发式触发条件。
- db 18 条与 `mock_db` 的 6 种 EXPLAIN 模式语义对应良好。

## 3. 遗留问题（不阻塞里程碑，留待抽查修订）

**P1 — 部分 chain 用例 golden 引入 mock 不存在的现象**：

| 用例 | golden 根因 | mock 是否支持 |
|---|---|---|
| chain-003 | 磁盘 I/O 饱和导致写阻塞 | ✗ mock_server 只有 disk percent，无 I/O 饱和 |
| chain-008 | 数据库锁等待 | ✗ mock_db 无锁等待模式 |
| chain-010 | 网络抖动 + 主从延迟 | ✗ mock 无网络/主从概念 |
| chain-002 | GC/swap 换页 | △ mock_server 有 swap 字段但无 GC |
| chain-004 | 连接池配置过小 | △ mock_logs 有连接耗尽日志但无「配置过小」语义 |

**影响**：运行时 agent 基于 mock 产不出这些根因，M2 用 LM-as-judge 对照打分时，这些用例会对所有实验组（基线 + 多智能体）一致偏低。对组间比较**公平**（不偏袒任何一方），但削弱区分度，也不利于论文数据的可解释性。

**处置建议**（M2 前或 M2 中择一）：
1. 把这几条 golden 改写回 mock 支持的现象范围（成本低，推荐）；
2. 或在 M6 扩充 mock 数据源时补上这些现象（成本高，属深度改造）。

**P2 — mock_server 用 `random`，非确定性**：`data/mock_server.py` 的 CPU/内存/磁盘用 `random.uniform`，跨 run 不可复现。server-014/015 等「正常」对照用例的 golden 只能写在语义层（「正常区间」而非固定值）。M2 做复现性时需处理（固定种子或改确定性 mock）。

**P3 — 数据源可能漂移**：`data/test_cases.json` 的 7 条已迁入评测集并带 golden，但旧文件仍在、`tests/test_diagnosis.py` 可能仍读旧文件。留待 M2 统一数据源时处理，本里程碑不动 tests。

## 4. 审查结论

**通过**。65 条用例格式合法、路由一致、分布合理，可作为 M2 评测 harness 的输入。P1/P2/P3 记录在案，均不阻塞进入 M2，其中 P1 建议在 M2 跑分前顺手修订。
