# M0 / Step4 — 补齐 requirements.txt 依赖

> 日期：2026-07-14 | 分支：feat/m0-foundation | 状态：已完成

## 1. Design 层

**问题**：`requirements.txt` 缺了两个已在用的依赖——`pyyaml`（`src/config.py` 读 YAML 配置在用）、`fpdf`（`scripts/gen_*_pdf.py` 生成方案 PDF 在用）。新环境 `pip install -r requirements.txt` 后仍会 `ImportError`，破坏「一次装好即可跑」。

**方案**：
- 补 `pyyaml`、`fpdf` 到核心依赖。
- M2 才用到的 `sqlalchemy`/`pymysql` **注释占位**——声明意图但不提前引入重依赖，避免误装。
- 按用途分组加中文注释，符合开发规范「注释用中文」。

**取舍**：为何不现在就放开 sqlalchemy/pymysql？因为 M0 阶段 DB 仍走 mock，装了也用不上，反而拖慢环境搭建、引入无谓依赖面。等 M2 真正接 MySQL 再取消注释。

## 2. Step 层

1. 读取现有 `requirements.txt`（原为 5 行无注释的裸依赖）。
2. 重写为分组结构：核心运行时 / 配置文档 / 真实数据源（占位）。
3. 补 `pyyaml>=6.0`、`fpdf>=1.7.2`。

## 3. Code 层

`requirements.txt`（核心改动）：
```
# ===== 配置与文档生成（M0 补齐）=====
pyyaml>=6.0          # src/config.py 读取 YAML 配置
fpdf>=1.7.2          # scripts/ 生成方案 PDF

# ===== 真实数据源（M2 接入 MySQL 时启用，先占位）=====
# sqlalchemy>=2.0.0
# pymysql>=1.1.0
```

## 4. Test 层

- 验证方式：`pip install -r requirements.txt` 应无报错；`python -c "import yaml, fpdf"` 应成功。
- 待统一在 M0 集成验证时随环境跑一次（见 review.md）。

## 5. Review 层（自查）

- [x] 版本用 `>=` 下限约束，符合可复现要求（后续锁版本在实验阶段做）
- [x] 未提前引入 M2 重依赖
- [x] 中文注释、分组清晰
- 结论：通过。遗留项——实验阶段（M3）需将 `>=` 改为锁定精确版本以保复现。
