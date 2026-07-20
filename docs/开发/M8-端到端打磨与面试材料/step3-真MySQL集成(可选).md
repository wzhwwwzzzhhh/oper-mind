# M8 Step3 — 真 MySQL 集成（可选）

> 状态：⚪ 计划（仅在有 buffer 时做）

## 背景

`src/tools/db_tools.py` 当前纯 mock（全从 `data.mock_db` import）。全栈 demo 靠可跑通的 UI+API+流式已能证明"真产品"，故真 MySQL 降为可选。

## 计划改动文件（守 CLAUDE.md 安全红线）

- `src/tools/db_tools.py` —— 加 pymysql 只读连接 + 参数化查询 + **禁 DDL/DML**，**保留 mock fallback**（api_key/连接缺失时回落）。
- config —— 只读账号连接串从**环境变量**读取，绝不进代码库。
- 可选：Docker seed 脚本灌 mock 表结构，出「mock vs 真实」对照。

## 待填

- [ ] 只读账号与连接方案
- [ ] fallback 策略
