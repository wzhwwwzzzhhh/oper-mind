# Step 2 — 评测记忆隔离、产物与统计验证

> 日期：2026-07-18
> 快照：工作区未提交；M3 `design.md` §3.5、§4、§6 的验收补充。

## Design

评测中的每条用例必须独立。运行一次 65 条 mock 评测后发现，领域 Agent 会把结论追加到
`data/memory.json`，后续用例又会把这些记录注入 prompt。这会造成样例顺序依赖、污染受 Git
跟踪的演示记忆文件，违反主实验的可复现要求。

因此把长期记忆作为系统装配的显式开关：日常 CLI/API 默认开启；`scripts/run_eval.py` 构建系统时
显式关闭。短期记忆仍保留在单个 Agent 的 ReAct 循环内，不跨用例持久化。

## Code

- `src/core/agent.py:19-110`
  - `BaseAgent` 新增 `enable_long_term_memory` 构造参数；关闭时不创建、注入或写入 `LongTermMemory`。
- `src/agents/db_agent.py:16-30`、`src/agents/server_agent.py:42-56`、`src/agents/log_agent.py:35-47`
  - 将该开关传递到基类，保留默认 `True`。
- `src/core/bootstrap.py:18-32`
  - `build_system()` 暴露开关并向三个领域 Agent 透传。
- `scripts/run_eval.py:63-64`
  - 评测固定用 `build_system(enable_long_term_memory=False)`。
- `tests/test_eval_memory_isolation.py:1-23`
  - 断言评测装配下 db/server/log 三个 Agent 的长期记忆均为 `None`。

## Test

1. 先新增隔离测试，在实现参数前运行：

   ```text
   TypeError: build_system() got an unexpected keyword argument 'enable_long_term_memory'
   ```

   证明测试确实覆盖未实现的接口。
2. 实现后运行：

   ```text
   .\.venv\Scripts\python.exe -m pytest tests\test_eval_memory_isolation.py tests\test_diagnosis.py -q
   2 passed in 3.45s
   ```
3. mock 评测验证：

   ```powershell
   $env:OPERMIND_API_KEY = "mock"
   .\.venv\Scripts\python.exe scripts\run_eval.py --arm m3-smoke --seed 42
   ```

   结果：65 条用例完成、`error_count=0`；评测前后 `data/memory.json` 的 SHA-256 均为
   `F8EB97C4A25C6C7B5F053EB3A228BA65E17BC9436818756FD8A46A796CBCFC5A`，没有写入。
4. 产物 `experiments/1652cc7cc4ea/meta.json` 已校验：`arm="m3-smoke"`、`is_mock=true`、
   `seed=42`、`total_cases=65`；`cases.jsonl` 为 65 行。
5. `load_metric()` 从该产物读取 `root_cause_score` 得到 65 个 case；`describe()` 返回：

   ```text
   n=65, mean=0.4417358523900179, std=0.180963913068543,
   95% CI=[0.39689519028458076, 0.486576514495455]
   ```

## Review

- 评测输出目录被 `.gitignore` 忽略，未纳入代码库。
- 首次发现问题的运行曾写入 `data/memory.json`；随后已恢复到本分支 HEAD，未保留污染数据。
- M3 真实模型“同 query 连跑两次”的人工 smoke 未执行，原因是会调用用户模型服务并产生用量；该项保留为
  真实模型配置就绪后的手动验收，不影响 mock 主实验的确定性证据。
