# M8 设计 — 端到端打磨与面试材料

> 里程碑：M8　|　分支：待建
> 创建日期：2026-07-20
> 状态：⚪ 计划

## 1. 目标

把前后端联调成一个能演示的完整产品，产出面试材料。**真 MySQL 降为可选 step**，仅在有 buffer 时做。

## 2. Step 分解

| Step | 内容 | 主要改动 |
|---|---|---|
| step1 | 端到端联调 + demo 录屏 | 跨 `src/app.py` + `src/frontend/` |
| step2 | pitch 与面试应答稿 | `docs/A-Plan/`（纯文档，非代码） |
| step3（可选） | 真 MySQL 只读集成 | `src/tools/db_tools.py`、config |

## 3. 验收

- 端到端 demo 可跑通（mock 模式必须稳，真实模式尽量）。
- 有 demo 录屏 + pitch 稿（STAR + 追问应答，分全栈/agent 两线）。
- 若做 step3：只读账号 + 参数化 + 禁 DDL/DML + mock fallback（守 CLAUDE.md 安全红线）。

## 4. 面试材料去向

pitch / 面试应答放 `docs/A-Plan/`，与开发日志分离。
