import { describe, expect, it } from 'vitest'
import type { TraceEvent } from '../types/api'
import { buildReplaySnapshot, strategyFromTrace, TRACE_FIXTURES } from './replay'

describe('buildReplaySnapshot', () => {
  it('direct 仅完成目标 db Agent，其余 Agent 标为跳过', () => {
    const fixture = TRACE_FIXTURES[0]
    const snapshot = buildReplaySnapshot(fixture.trace, fixture.strategy, 2)

    expect(snapshot.route).toBe('done')
    expect(snapshot.agents.db).toBe('done')
    expect(snapshot.agents.server).toBe('skipped')
    expect(snapshot.agents.log).toBe('skipped')
    expect(snapshot.conflict).toBe('skipped')
  })

  it('chain 按 trace 顺序逐层完成 Agent', () => {
    const fixture = TRACE_FIXTURES[1]
    const afterServer = buildReplaySnapshot(fixture.trace, fixture.strategy, 2)
    const afterDb = buildReplaySnapshot(fixture.trace, fixture.strategy, 3)

    expect(afterServer.agents.server).toBe('done')
    expect(afterServer.agents.db).toBe('pending')
    expect(afterDb.agents.db).toBe('done')
    expect(afterDb.agents.log).toBe('pending')
  })

  it('parallel 仅在 debate trace 到达时标记辩论完成', () => {
    const fixture = TRACE_FIXTURES[2]
    const afterParallel = buildReplaySnapshot(fixture.trace, fixture.strategy, 2)
    const afterConflict = buildReplaySnapshot(fixture.trace, fixture.strategy, 3)
    const afterDebate = buildReplaySnapshot(fixture.trace, fixture.strategy, 4)

    expect(afterParallel.agents).toEqual({ db: 'done', server: 'done', log: 'done' })
    expect(afterConflict.conflict).toBe('done')
    expect(afterConflict.debate).toBe('pending')
    expect(afterDebate.debate).toBe('done')
  })

  it('只有 conflict trace 明确分歧=false 时才跳过 Debate', () => {
    const trace: TraceEvent[] = [
      { type: 'route_decided', node: 'route', detail: '兜底关键词路由 → parallel', timestamp: '2026-07-24T00:00:01+00:00' },
      { type: 'agent_done', node: 'parallel', detail: "并发 Agent=['db', 'server', 'log']", timestamp: '2026-07-24T00:00:02+00:00' },
      { type: 'conflict_checked', node: 'conflict_check', detail: '分歧=False', timestamp: '2026-07-24T00:00:03+00:00' },
    ]

    expect(buildReplaySnapshot(trace, 'parallel').debate).toBe('skipped')
  })
})

describe('strategyFromTrace', () => {
  it('从 route trace 提取真实诊断的路由策略', () => {
    expect(strategyFromTrace(TRACE_FIXTURES[0].trace)).toBe('direct')
    expect(strategyFromTrace(TRACE_FIXTURES[1].trace)).toBe('chain')
    expect(strategyFromTrace(TRACE_FIXTURES[2].trace)).toBe('parallel')
  })

  it('没有可识别的 route trace 时返回 unknown', () => {
    expect(strategyFromTrace([])).toBe('unknown')
  })
})
