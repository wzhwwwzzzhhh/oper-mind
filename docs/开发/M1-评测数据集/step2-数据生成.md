# M1 · Step2 — 65 条评测用例生成

> 里程碑：M1　|　分支：`feat/m1-dataset`　|　日期：2026-07-14
> 关联：`design.md`、`step1-schema与校验器.md`

---

## 1. 目标

在 step1 的契约（`data/eval/schema.py`）之上，生成 50–100 条评测用例，覆盖四个领域与三种路由策略，每条带 golden 标注，全部通过 `validate.py` 的结构 + 路由一致性双层校验。

## 2. 做法：四域并行造数

四个领域相互独立，派 4 个 agent 并行生成，各写一个分片文件，各自跑 `validate.py` 迭代到零错误再交付：

| 域 | 文件（中间产物，已删） | 条数 | 策略 | 说明 |
|---|---|---|---|---|
| db | cases_db.jsonl | 18 | direct | 7 条迁移自 `data/test_cases.json` + 11 条新造 |
| server | cases_server.jsonl | 15 | direct | CPU/内存/磁盘/进程 |
| log | cases_log.jsonl | 12 | direct | 连接池/OOM/线程池/超时 |
| compound | cases_compound.jsonl | 20 | chain×10 + parallel×10 | 跨域复合故障，含 5 条 debate |

合并为唯一可信源 `data/eval/cases.jsonl`（65 行），删除 4 个分片与一次性生成器脚本，避免多源漂移。

## 3. 最终分布（validate.py 全量输出）

```
用例总数：65
  domain            : compound=20，db=18，log=12，server=15
  expected_strategy : chain=10，direct=45，parallel=10
  difficulty        : easy=19，hard=15，medium=31
  source            : seed=7，synthetic=58
  expects_debate    : true=5

✅ 校验通过：65 条用例全部合法，路由与运行时一致。
```

## 4. 关键约束的落地

**路由关键词陷阱**——所有 agent 都踩过、也都规避了：

- `_CHAIN_KW` 含「慢」子串：db/server/log 的 direct 用例一律避开「慢/卡/故障/排查/定位/不稳定」，改用「执行效率低/响应时间长/CPU 使用率高」等中性词。
- `mysqld` 含 `sql` 子串：server 用例把 `mysqld` 只放进 golden 字段，query 用「单个进程 CPU 独占」等表述，避免误命中 db。
- compound 反过来利用触发词：chain 用例主动含「很慢/排查/故障」，parallel 用例含「体检/全面/巡检/大促」。

**golden 锚定 mock**——golden 根因尽量对齐 `mock_db` 的 6 种 EXPLAIN 模式、`mock_logs` 的固定日志行、`mock_server` 的进程/资源现象。

## 5. 交付物

- `data/eval/cases.jsonl` — 65 条，唯一可信源
