import { useEffect, useMemo, useRef } from 'react'
import { init, use } from 'echarts/core'
import { BarChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { BarSeriesOption, EChartsCoreOption } from 'echarts'
import {
  M5_CASE_GROUPS,
  M5_EXPERIMENTS,
  formatDelta,
  percent,
  percentagePointDelta,
  relativeChange,
  secondsFromMs,
} from '../../data/m5Experiment'

use([BarChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

export type MetricId = 'rootCause' | 'keyPointsRecall' | 'routeHit' | 'latencyMs' | 'tokens'

export interface GlobalMetric {
  id: MetricId
  label: string
  detail: string
  unit: string
  single: number
  full: number
  format: (value: number) => string
  delta: string
  positive: boolean
}

const CHART_TEXT = '#c8d5ea'
const CHART_MUTED = '#8b9bb6'
const SINGLE_COLOR = '#7586a5'
const FULL_COLOR = '#5ce1c6'

function globalMetrics(): GlobalMetric[] {
  const single = M5_EXPERIMENTS.single_agent
  const full = M5_EXPERIMENTS.full
  return [
    {
      id: 'rootCause',
      label: '根因定位',
      detail: 'mean root-cause score',
      unit: '%',
      single: percent(single.rootCause),
      full: percent(full.rootCause),
      format: (value) => `${value}%`,
      delta: `${formatDelta(percentagePointDelta(single.rootCause, full.rootCause))} / ${formatDelta(relativeChange(single.rootCause, full.rootCause), '%')}`,
      positive: true,
    },
    {
      id: 'keyPointsRecall',
      label: '关键点召回',
      detail: 'mean key-point recall',
      unit: '%',
      single: percent(single.keyPointsRecall),
      full: percent(full.keyPointsRecall),
      format: (value) => `${value}%`,
      delta: `${formatDelta(percentagePointDelta(single.keyPointsRecall, full.keyPointsRecall))} / ${formatDelta(relativeChange(single.keyPointsRecall, full.keyPointsRecall), '%')}`,
      positive: true,
    },
    {
      id: 'routeHit',
      label: '路由命中',
      detail: 'expected strategy hit rate',
      unit: '%',
      single: percent(single.routeHit),
      full: percent(full.routeHit),
      format: (value) => `${value}%`,
      delta: formatDelta(percentagePointDelta(single.routeHit, full.routeHit)),
      positive: true,
    },
    {
      id: 'latencyMs',
      label: '平均延迟',
      detail: 'mean end-to-end latency',
      unit: 's',
      single: secondsFromMs(single.latencyMs),
      full: secondsFromMs(full.latencyMs),
      format: (value) => `${value}s`,
      delta: formatDelta(secondsFromMs(full.latencyMs - single.latencyMs), 's'),
      positive: false,
    },
    {
      id: 'tokens',
      label: '诊断 Token',
      detail: 'judge tokens excluded',
      unit: 'k',
      single: Number((single.tokens / 1000).toFixed(1)),
      full: Number((full.tokens / 1000).toFixed(1)),
      format: (value) => `${value}k`,
      delta: formatDelta(relativeChange(single.tokens, full.tokens), '%'),
      positive: false,
    },
  ]
}

/** 生成全局质量 / 成本图表 option，单独导出以便无 DOM 单测。 */
export function createGlobalOption(metrics: GlobalMetric[]): EChartsCoreOption {
  const qualityMetrics = metrics.slice(0, 3)
  const costMetrics = metrics.slice(3)
  const series = (name: string, data: number[], axisIndex: number): BarSeriesOption => ({
    name,
    type: 'bar',
    xAxisIndex: axisIndex,
    yAxisIndex: axisIndex,
    barMaxWidth: 24,
    itemStyle: { color: name === 'Single agent' ? SINGLE_COLOR : FULL_COLOR, borderRadius: [4, 4, 0, 0] },
    data,
  })
  return {
    backgroundColor: 'transparent',
    legend: { top: 0, right: 0, textStyle: { color: CHART_MUTED, fontSize: 11 }, itemWidth: 10, itemHeight: 10 },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, backgroundColor: '#101b2e', borderColor: '#263956', textStyle: { color: CHART_TEXT } },
    grid: [
      { left: 42, right: '55%', top: 42, bottom: 42 },
      { left: '57%', right: 22, top: 42, bottom: 42 },
    ],
    xAxis: [
      { type: 'category', gridIndex: 0, data: qualityMetrics.map((metric) => metric.label), axisLine: { lineStyle: { color: '#263956' } }, axisLabel: { color: CHART_MUTED, fontSize: 10 } },
      { type: 'category', gridIndex: 1, data: costMetrics.map((metric) => metric.label), axisLine: { lineStyle: { color: '#263956' } }, axisLabel: { color: CHART_MUTED, fontSize: 10 } },
    ],
    yAxis: [
      { type: 'value', gridIndex: 0, min: 0, max: 100, axisLabel: { color: CHART_MUTED, formatter: '{value}%' }, splitLine: { lineStyle: { color: 'rgba(43, 62, 94, .5)' } } },
      { type: 'value', gridIndex: 1, min: 0, axisLabel: { color: CHART_MUTED }, splitLine: { lineStyle: { color: 'rgba(43, 62, 94, .5)' } } },
    ],
    series: [
      series('Single agent', qualityMetrics.map((metric) => metric.single), 0),
      series('Full multi-agent', qualityMetrics.map((metric) => metric.full), 0),
      series('Single agent', costMetrics.map((metric) => metric.single), 1),
      series('Full multi-agent', costMetrics.map((metric) => metric.full), 1),
    ],
  }
}

/** 生成按 case_group 分层的根因得分 option，展示绝对得分而非夸大相对倍数。 */
export function createCaseGroupOption(): EChartsCoreOption {
  return {
    backgroundColor: 'transparent',
    legend: { top: 0, right: 0, textStyle: { color: CHART_MUTED, fontSize: 11 }, itemWidth: 10, itemHeight: 10 },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: '#101b2e',
      borderColor: '#263956',
      textStyle: { color: CHART_TEXT },
      formatter: (params: unknown) => {
        const index = (params as Array<{ dataIndex: number }>)[0]?.dataIndex ?? 0
        const group = M5_CASE_GROUPS[index]
        return `${group.label} · n=${group.count}<br/>${(params as Array<{ marker: string; seriesName: string; value: number }>).map((item) => `${item.marker}${item.seriesName}: ${(item.value * 100).toFixed(1)}%`).join('<br/>')}`
      },
    },
    grid: { left: 42, right: 22, top: 42, bottom: 64 },
    xAxis: {
      type: 'category',
      data: M5_CASE_GROUPS.map((group) => `${group.label}\nn=${group.count}`),
      axisLine: { lineStyle: { color: '#263956' } },
      axisLabel: { color: CHART_MUTED, fontSize: 10, lineHeight: 15 },
    },
    yAxis: { type: 'value', min: 0, max: 1, axisLabel: { color: CHART_MUTED, formatter: (value: number) => `${Math.round(value * 100)}%` }, splitLine: { lineStyle: { color: 'rgba(43, 62, 94, .5)' } } },
    series: [
      { name: 'Single agent', type: 'bar', barMaxWidth: 30, itemStyle: { color: SINGLE_COLOR, borderRadius: [4, 4, 0, 0] }, data: M5_CASE_GROUPS.map((group) => group.singleAgent) },
      { name: 'Full multi-agent', type: 'bar', barMaxWidth: 30, itemStyle: { color: FULL_COLOR, borderRadius: [4, 4, 0, 0] }, data: M5_CASE_GROUPS.map((group) => group.full) },
    ],
  }
}

function useChart(option: EChartsCoreOption): React.RefObject<HTMLDivElement | null> {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = containerRef.current
    if (!element) return undefined
    const chart = init(element, undefined, { renderer: 'canvas' })
    chart.setOption(option)
    const resize = () => chart.resize()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(resize)
    observer?.observe(element)
    window.addEventListener('resize', resize)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', resize)
      chart.dispose()
    }
  }, [option])

  return containerRef
}

export function MetricsDashboard() {
  const metrics = useMemo(globalMetrics, [])
  const globalOption = useMemo(() => createGlobalOption(metrics), [metrics])
  const caseGroupOption = useMemo(() => createCaseGroupOption(), [])
  const globalChartRef = useChart(globalOption)
  const caseGroupChartRef = useChart(caseGroupOption)
  const single = M5_EXPERIMENTS.single_agent
  const full = M5_EXPERIMENTS.full

  return (
    <section className="metrics-dashboard" aria-labelledby="metrics-title">
      <div className="metrics-heading">
        <div>
          <span className="eyebrow">M5 EVIDENCE DASHBOARD</span>
          <h2 id="metrics-title">多 Agent 的收益与代价</h2>
          <p>基于两臂真实跑批的 77 例对比。图表显示平均值与分组切片，不代表显著性检验。</p>
        </div>
        <span className="evidence-badge">REAL RUN · SEED 42</span>
      </div>

      <div className="metric-card-grid">
        {metrics.map((metric) => (
          <article className={`metric-card ${metric.positive ? 'gain' : 'cost'}`} key={metric.id}>
            <span>{metric.label}</span>
            <strong>{metric.format(metric.full)}</strong>
            <small>single {metric.format(metric.single)} → full {metric.format(metric.full)}</small>
            <em>{metric.delta}</em>
          </article>
        ))}
      </div>

      <div className="metrics-chart-grid">
        <article className="metrics-chart-card">
          <div className="chart-heading"><div><span className="eyebrow">GLOBAL</span><h3>质量与成本</h3></div><small>质量：% · 成本：秒 / 千 token</small></div>
          <div className="echarts-canvas" ref={globalChartRef} aria-label="全局质量与成本对比图" />
        </article>
        <article className="metrics-chart-card">
          <div className="chart-heading"><div><span className="eyebrow">CASE GROUP</span><h3>根因定位分层</h3></div><small>均值 · 各组 n 已标注</small></div>
          <div className="echarts-canvas" ref={caseGroupChartRef} aria-label="按用例组的根因定位对比图" />
        </article>
      </div>

      <div className="evidence-detail-grid">
        <article className="evidence-note">
          <span className="eyebrow">可辩护结论</span>
          <ul>
            <li>跨源复合：根因得分 <strong>{formatDelta(percentagePointDelta(0.27, 0.765))}</strong>，是协作的主要收益区。</li>
            <li>真分歧 + 辩论：根因得分 <strong>{formatDelta(percentagePointDelta(0.4166666666666667, 0.7333333333333334))}</strong>。</li>
            <li>表象误导：<strong>0.0pp</strong>，多 Agent 并不自动优于单模型。</li>
            <li>单域故障：<strong>+1.6pp</strong>，协作开销在此收益有限。</li>
          </ul>
        </article>
        <article className="evidence-note provenance">
          <span className="eyebrow">实验条件与限制</span>
          <p>single `{single.configHash}` 与 full `{full.configHash}`；诊断模型 {single.model}，独立裁判 {single.judgeModel}。</p>
          <p>两臂各 {single.totalCases} 例，均非 mock、裁判非 stub、错误数为 0；仅一次 seed={single.seed} 真实跑批，未展示未运行的消融或统计显著性。</p>
          <p>来源：<code>experiments/&lt;hash&gt;/meta.json</code> 与 <code>summary.json</code>；前端仅保留已核验摘要。</p>
        </article>
      </div>
    </section>
  )
}
