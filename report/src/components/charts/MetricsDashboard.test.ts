import { describe, expect, it } from 'vitest'
import { createCaseGroupOption, createGlobalOption } from './MetricsDashboard'
import { M5_EXPERIMENTS, percent, secondsFromMs } from '../../data/m5Experiment'

describe('M5 ECharts option', () => {
  it('全局图表按质量和成本拆分坐标轴，并保持两臂数据可核对', () => {
    const single = M5_EXPERIMENTS.single_agent
    const full = M5_EXPERIMENTS.full
    const option = createGlobalOption([
      { id: 'rootCause', label: '根因定位', detail: '', unit: '%', single: percent(single.rootCause), full: percent(full.rootCause), format: String, delta: '', positive: true },
      { id: 'keyPointsRecall', label: '关键点召回', detail: '', unit: '%', single: percent(single.keyPointsRecall), full: percent(full.keyPointsRecall), format: String, delta: '', positive: true },
      { id: 'routeHit', label: '路由命中', detail: '', unit: '%', single: percent(single.routeHit), full: percent(full.routeHit), format: String, delta: '', positive: true },
      { id: 'latencyMs', label: '平均延迟', detail: '', unit: 's', single: secondsFromMs(single.latencyMs), full: secondsFromMs(full.latencyMs), format: String, delta: '', positive: false },
      { id: 'tokens', label: '诊断 Token', detail: '', unit: 'k', single: Number((single.tokens / 1000).toFixed(1)), full: Number((full.tokens / 1000).toFixed(1)), format: String, delta: '', positive: false },
    ])

    expect(option.xAxis).toHaveLength(2)
    expect(option.series).toHaveLength(4)
  })

  it('分组图表保留四个 case_group 及样本量标签', () => {
    const option = createCaseGroupOption()
    const xAxis = option.xAxis as { data: string[] }

    expect(xAxis.data).toEqual(['跨源复合\nn=20', '真分歧 + 辩论\nn=6', '表象误导\nn=6', '单域故障\nn=45'])
    expect(option.series).toHaveLength(2)
  })
})
