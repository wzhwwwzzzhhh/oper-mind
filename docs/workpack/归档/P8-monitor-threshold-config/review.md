# P8-monitor-threshold-config · 独立代码审查

> 审查方式：只读子代理独立审查（与开发视角分离），基于 `git diff`、plan/PRD/Design、关键实现文件。
> 审查日期：2026-08-15

## 总体

**初审结论：FAIL（1 条 P1）→ 已修复 → 复审通过（PASS）**

- 初审发现 [P1]：服务详情页"运行趋势"异常采样点标记仍使用旧的按服务类型硬编码规则，未按 Design §2.3/§2.5 读取阈值配置复算（AC5 历史侧未落实）。
- 修复内容：
  1. `ServiceDetailPage.tsx` 新增 `windowed_metric_sums` / `is_anomalous_sample` / `anomaly_reasons`（与后端 `_windowed_metric_sums`/`_trend_summary` 同一 §2.3 文字契约：含两端窗口、window=0 只含自身、null 计 0、首样本不判可用性异常、相邻既有样本比较）；
  2. 页面级 `thresholds_query` 接入趋势卡片，异常标记与原因列表按配置计算（保存后经 React Query 共享缓存自动刷新）；
  3. 新增前端交互测试 `配置阈值后运行趋势异常标记按配置复算，与后端一致（AC5）`（窗口 10 分钟聚合：1+2=3 ≥ 3 仅末点异常）。
- 复审：P1 已消除，配套测试全绿（ServiceDetailPage 10/10）。

## 发现与处置

| 级别 | 发现 | 处置 |
|---|---|---|
| P1 | 前端趋势异常标记未按配置复算（AC5/Design §2.5） | 已修复 + 一致性测试（见上） |
| P2 | 窗口下拉固定预设 [0,5,10,15,30]，API 接受 [0,1440]，自定义值回显无匹配 option | 已修复：值不在预设集时补"自定义 N 分钟"option |
| P2 | 阈值输入空值被静默当 0（恒异常风险），无入口清回 null | 已修复：空输入 = 不关注（与勾选开关语义一致） |
| P2 | 降级范围未澄清（仅校验类损坏回退默认，DB 故障按既有语义上抛） | 已修复：`_load_threshold_config` docstring 明确边界 |
| P3 | 接口清单 v1 合计与装饰器数有口径偏差 | 已核对：实测 operations=49，文档按自身表格口径（46，含本包 +2）；绝对数偏差为既有口径漂移（#60 等交付未回写），非本包引入，记录在案 |
| P3 | 测试助手 `_sample` 对 Redis 填 PG 语义标量 0 而非 null | 已修复：Redis 样本显式 `slow=None, timeout=None`，镜像真实采样不变量 |
| P3 | `generated.ts` 阈值字段生成类型宽松（`unknown`） | 接受：生成产物（`npm run generate:api` 生成），client.ts 手写类型为运行时事实源；禁止手改 generated.ts |

## 结论

**PASS**——P0/P1 已清零（P1 修复并有测试锁定），P2 全部修复，P3 处理完毕（2 项修复、1 项记录、1 项接受生成产物）。后端 506 passed / 2 skipped；前端 typecheck、build 通过，ServiceDetailPage 10/10、MonitoringOverviewPage 7/7；全量前端失败集与基线一致（既有环境性时序 flakiness，与本工作包无关）。
