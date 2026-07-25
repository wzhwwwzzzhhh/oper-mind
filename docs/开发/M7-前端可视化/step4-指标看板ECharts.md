# M7 Step4 — M5 指标看板（ECharts）

> 日期：2026-07-25　|　状态：✅ 通过，待提交　|　分支：`feat/m7-frontend-visualization`
> 稳定基线：`b8d5e51 feat: 完成M7 SSE实时增量与降级`

## Design

M5 已完成真实对比实验。前端看板只呈现两个可追溯的真实产物：`single_agent`（`6f53f145fe33`）与 `full`（`a2752bd48380`）。二者均使用 seed 42、诊断模型 `deepseek-v4-flash`、独立裁判 `deepseek-v4-pro`、77 例、`judge_is_stub=false`、`error_count=0`。

本 Step 用 ECharts 展示：全局质量/成本对比、按 case_group 的 root-cause 分层收益，以及每组样本数与限制说明。前端展示数据从受控 TS 数据模块读取，数据字段与两份 `experiments/<hash>/meta.json`、`summary.json` 核对；不在浏览器读取本地实验目录，不新增后端接口，也不伪造“统计显著性”或未运行的消融结论。

## Step

1. 安装并封装唯一图表依赖 ECharts；组件卸载时 dispose，容器/窗口尺寸变化时 resize。
2. 将 M5 两份真实 summary / meta 的已核验字段写入带来源元数据的只读前端数据模块，并用纯函数派生展示指标。
3. 展示全局 root cause、key-point recall、route hit、latency、tokens 对比；质量与成本分开表达。
4. 展示 case_group root-cause 对比与 delta，同时标明每组样本数。
5. 展示实验条件、数据来源、已知限制和诚实结论；不把 77 例单次真实跑批伪装成显著性结论。
6. 补充数据派生与 ECharts option 单测，执行 typecheck / build，独立 Review 后提交。

## Code

- `src/frontend/src/data/m5Experiment.ts:1-103`：两臂真实跑批的可追溯摘要、四个 case_group 及百分点/相对增益/时延派生函数；原始实验目录不进入浏览器或提交。
- `src/frontend/src/data/m5Experiment.test.ts:1-45`：实验条件、全局收益与分组零收益边界的回归测试。
- `src/frontend/src/components/charts/MetricsDashboard.tsx:1-255`：按需注册 ECharts，生成全局质量/成本和 case_group option，容器 resize 时重绘、卸载 dispose，并展示数据来源及局限。
- `src/frontend/src/components/charts/MetricsDashboard.test.ts:1-29`：图表 option 的双坐标轴和分组样本标签测试。
- `src/frontend/src/App.tsx`、`src/frontend/src/styles/global.css`：接入看板、M7.4 文案与响应式视觉样式。
- `src/frontend/package.json`、`src/frontend/package-lock.json`：新增唯一运行时依赖 `echarts@^6.0.0`。

## Test

```text
npm.cmd run test       → 5 files / 23 tests passed
npm.cmd run typecheck  → passed
npm.cmd run build      → passed
git diff --check       → passed
```

生产构建成功，但 ECharts 图表 chunk 为 717.90 kB（gzip 238.15 kB），超过 Vite 500 kB 提示阈值；当前单页答辩应用可用，M7.5 评估动态加载 / 拆包。M7.5 也可为全局图补充带单位的自定义 tooltip，提升演示可读性。

## Review

- 独立审查人：Ohm（2026-07-25）。
- 结论：无 P1/P2。双臂 meta / summary、四组 case_group 数值与样本数均逐项一致；pp/相对增益、延迟与诊断 token 成本口径正确；质量与成本分图展示；图表使用 `ResizeObserver`、window resize 与 cleanup dispose。
- 诚实性核对：页面明确 n=77、seed=42、诊断/独立裁判模型、非 mock、裁判非 stub、0 错误、单次跑批及“不代表显著性检验”；未展示未运行消融，且明确 mislead 无收益、单域收益有限。
- P3：ECharts 图表包体积与全局 tooltip 单位可读性，已列入 M7.5，不阻塞本 Step。
