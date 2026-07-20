# M5 Step2 — 多故障 mock 世界

> 状态：⚪ 计划（待开工时填写）

## 背景

当前整个 mock 世界只有一起故障（`data/mock_logs.py` 唯一时间线 OOM→连接池耗尽→orders 慢查询；`data/mock_db.py` 只有 orders 缺索引场景）。所有 compound 用例答案恒定，多 Agent 无从证明价值。

## 计划改动文件

- 新增 `data/scenarios.py` —— 定义多起互不相同的故障场景（如：①磁盘写满、②纯内存泄漏、③连接数配置错误），支持按 case 切换。
- `data/mock_db.py` / `data/mock_logs.py` / `data/mock_server.py` —— 从全局单份改为可按场景返回不同现象。

## 待填

- [ ] 3–4 起故障的根因/现象设计（确保根因互不相同、不都指向 orders 索引）
- [ ] 场景切换机制（如何让某条 case 绑定某个场景）
- [ ] Mock 纪律：保持确定性，答辩可复现
