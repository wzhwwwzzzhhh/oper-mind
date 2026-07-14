# M1 · Step1 — 评测契约与校验器

> 里程碑：M1　|　分支：`feat/m1-dataset`　|　日期：2026-07-14
> 关联：`design.md` → 第 3 节（schema 契约）、第 4 节（路由一致性约束）

---

## 1. 做了什么

评测数据集的地基是「契约」——每条用例长什么样、必须满足哪些约束。这一步不派 agent，作为单一可信源亲自实现：

| 文件 | 职责 |
|---|---|
| `data/eval/schema.py` | 用 Pydantic 定死 `EvalCase` 结构与跨字段约束 |
| `data/eval/validate.py` | 两层校验：结构校验 + 路由一致性校验 |

## 2. 关键设计

### 2.1 schema 契约（`data/eval/schema.py`）

`EvalCase` 字段与运行时路由契约（`src/core/graph.py`）对齐：

- `Domain = Literal["db", "server", "log", "compound"]`
- `Strategy = Literal["direct", "chain", "parallel"]`
- `VALID_AGENTS = {"db", "server", "log"}`（见 `src/core/bootstrap.build_system`）

跨字段一致性由 `model_post_init` 强制（`schema.py`）：

```python
if self.expected_strategy == "direct" and n != 1:
    raise ValueError(...)          # direct 只能命中 1 个 agent
if self.expected_strategy in ("chain", "parallel") and n < 2:
    raise ValueError(...)          # chain/parallel 至少 2 个
if self.expects_debate and self.expected_strategy != "parallel":
    raise ValueError(...)          # 只有 parallel 可能触发辩论
```

### 2.2 路由一致性校验（`data/eval/validate.py`）

最关键的设计决策：**直接 import 运行时的路由函数，而非复制逻辑**——

```python
from src.core.graph import _keyword_strategy, _keyword_target
```

这样保证「校验用例是否会命中期望策略」与「运行时实际怎么路由」是同源的。mock 模式走关键词兜底路由，所以每条 query 的关键词必须真能命中 `expected_strategy`，否则冒烟/评测会路由错。

## 3. 踩到的坑：关键词路由陷阱

`_CHAIN_KW` 含 `"慢"`，而 DB 用例天然想用「慢查询」描述 → 任何含「慢」的 query 都被路由成 chain 而非 direct。这正是路由一致性校验要挡的问题。

造数据时的规避手法（写入各域 agent 的约束）：
- DB direct 用例改用「执行效率低 / 响应时间长 / 性能差」等中性词，避开「慢/卡/故障/排查/定位/不稳定」
- Server 用例避开 `mysqld`（`.lower()` 后含 `sql` 子串，会命中 SQL 关键词 → 2 域 → 被迫 chain）
- Log 用例把「线程池/内存/磁盘」等跨域现象只写进 golden，不写进 query

## 4. 自检

```
$ python data/eval/validate.py
[self-check] schema+validate 导入正常
```

导入无误，接口（`load_cases` / `check_routing`）就绪，供各域 agent 造数时自跑迭代。
