import { describe, expect, it } from 'vitest'
import {
  M5_CASE_GROUPS,
  M5_EXPERIMENTS,
  percent,
  percentagePointDelta,
  relativeChange,
  secondsFromMs,
} from './m5Experiment'

describe('M5 实验摘要', () => {
  it('只包含可追溯的两臂真实跑批，且实验条件一致', () => {
    const single = M5_EXPERIMENTS.single_agent
    const full = M5_EXPERIMENTS.full

    expect(single.configHash).toBe('6f53f145fe33')
    expect(full.configHash).toBe('a2752bd48380')
    expect(single.totalCases).toBe(77)
    expect(full.totalCases).toBe(77)
    expect(single.seed).toBe(full.seed)
    expect(single.model).toBe(full.model)
    expect(single.judgeModel).toBe(full.judgeModel)
    expect(single.judgeIsStub).toBe(false)
    expect(full.judgeIsStub).toBe(false)
    expect(single.errorCount).toBe(0)
    expect(full.errorCount).toBe(0)
  })

  it('保留 M5 的全局质量收益和成本数据', () => {
    const single = M5_EXPERIMENTS.single_agent
    const full = M5_EXPERIMENTS.full

    expect(percentagePointDelta(single.rootCause, full.rootCause)).toBe(16.2)
    expect(relativeChange(single.rootCause, full.rootCause)).toBe(29)
    expect(percentagePointDelta(single.keyPointsRecall, full.keyPointsRecall)).toBe(18.2)
    expect(percent(full.routeHit)).toBe(90)
    expect(secondsFromMs(full.latencyMs)).toBe(76.5)
  })

  it('保留分组样本数、根因得分与诚实的零收益组', () => {
    const compound = M5_CASE_GROUPS.find((group) => group.id === 'legacy_compound')
    const mislead = M5_CASE_GROUPS.find((group) => group.id === 'mislead')

    expect(compound?.count).toBe(20)
    expect(percentagePointDelta(compound?.singleAgent ?? 0, compound?.full ?? 0)).toBe(49.5)
    expect(mislead?.count).toBe(6)
    expect(percentagePointDelta(mislead?.singleAgent ?? 0, mislead?.full ?? 0)).toBe(0)
  })
})
