# M5 Step3 — 区分度用例集

> 状态：⚪ 计划（待开工时填写）

## 背景

要让「多 Agent vs 单模型」出现差距，必须有**单模型会答错、多 Agent 交叉验证能纠偏**的用例。

## 两类关键用例

1. **表象误导型**：扎眼的表象（如 CPU 95%）指向错误根因（真因在磁盘 IO），单 Agent 停在表象即错，chain/debate 交叉印证才挖到真因。
2. **真分歧型**：三源指向不同根因，`expects_debate=true`，考察辩论收敛能力（当前那些"都指向 orders 索引"的假分歧要替换）。

## 计划改动文件

- `data/eval/cases.jsonl` —— 新增表象误导 + 真分歧用例（真分歧扩到 15+）。
- `data/eval/schema.py` / `data/eval/validate.py` —— 若需要新增字段（如注入的误导现象标记）则同步。

## 待填

- [ ] 用例清单（绑定 step2 的多故障场景）
- [ ] golden_root_cause / golden_key_points（确保不可互换）
- [ ] validate 一致性校验通过
