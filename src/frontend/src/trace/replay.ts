import type { DiagnoseResponse, TraceEvent } from '../types/api'

export type AgentId = 'db' | 'server' | 'log'
export type NodeState = 'pending' | 'done' | 'skipped'

export interface TraceFixture {
  id: 'direct' | 'chain' | 'parallel'
  label: string
  strategy: 'direct' | 'chain' | 'parallel'
  trace: TraceEvent[]
}

export interface ReplaySnapshot {
  strategy: string
  route: NodeState
  agents: Record<AgentId, NodeState>
  conflict: NodeState
  debate: NodeState
  report: NodeState
  reflection: NodeState
}

const AGENTS: AgentId[] = ['db', 'server', 'log']

function event(type: TraceEvent['type'], node: string, detail: string, index: number): TraceEvent {
  return {
    type,
    node,
    detail,
    timestamp: `2026-07-24T00:00:0${index}+00:00`,
  }
}

export const TRACE_FIXTURES: TraceFixture[] = [
  {
    id: 'direct',
    label: '直达 · 慢 SQL',
    strategy: 'direct',
    trace: [
      event('route_decided', 'route', '兜底关键词路由 → direct', 1),
      event('agent_done', 'direct', '目标 Agent=db', 2),
      event('report', 'report', '生成初稿', 3),
      event('reflection', 'reflection', '复审通过', 4),
    ],
  },
  {
    id: 'chain',
    label: '链式 · 系统超时',
    strategy: 'chain',
    trace: [
      event('route_decided', 'route', '兜底关键词路由 → chain', 1),
      event('agent_done', 'chain', '逐层:server', 2),
      event('agent_done', 'chain', '逐层:db', 3),
      event('agent_done', 'chain', '逐层:log', 4),
      event('report', 'report', '生成初稿', 5),
      event('reflection', 'reflection', '复审通过', 6),
    ],
  },
  {
    id: 'parallel',
    label: '并行 · 大促体检',
    strategy: 'parallel',
    trace: [
      event('route_decided', 'route', '兜底关键词路由 → parallel', 1),
      event('agent_done', 'parallel', "并发 Agent=['db', 'server', 'log']", 2),
      event('conflict_checked', 'conflict_check', '分歧=true', 3),
      event('debate_round', 'debate', '辩论裁决完成', 4),
      event('report', 'report', '生成初稿', 5),
      event('reflection', 'reflection', '复审通过', 6),
    ],
  },
]

export function strategyFromResponse(response: DiagnoseResponse | null): string {
  return response?.strategy || ''
}

/** 从 Coordinator 路由 trace 中还原策略，避免真实 trace 使用演示样例的策略。 */
export function strategyFromTrace(trace: TraceEvent[]): string {
  const route = trace.find((item) => item.node === 'route')
  const detail = route?.detail.toLowerCase() ?? ''

  if (detail.includes('direct')) return 'direct'
  if (detail.includes('chain')) return 'chain'
  if (detail.includes('parallel')) return 'parallel'
  return 'unknown'
}

function containsAgent(detail: string, agent: AgentId): boolean {
  return detail.toLowerCase().includes(agent)
}

function skippedAgents(strategy: string, agents: Record<AgentId, NodeState>): Record<AgentId, NodeState> {
  if (strategy !== 'direct') return agents
  const completed = AGENTS.some((agent) => agents[agent] === 'done')
  if (!completed) return agents
  return AGENTS.reduce<Record<AgentId, NodeState>>((result, agent) => {
    result[agent] = agents[agent] === 'done' ? 'done' : 'skipped'
    return result
  }, { db: 'pending', server: 'pending', log: 'pending' })
}

export function buildReplaySnapshot(
  trace: TraceEvent[],
  strategy: string,
  visibleCount = trace.length,
): ReplaySnapshot {
  const visibleTrace = trace.slice(0, visibleCount)
  const agents: Record<AgentId, NodeState> = { db: 'pending', server: 'pending', log: 'pending' }
  let route: NodeState = 'pending'
  let conflict: NodeState = 'pending'
  let hasConflict: boolean | null = null
  let debate: NodeState = 'pending'
  let report: NodeState = 'pending'
  let reflection: NodeState = 'pending'

  for (const item of visibleTrace) {
    if (item.node === 'route') route = 'done'
    if (item.node === 'direct') {
      for (const agent of AGENTS) if (containsAgent(item.detail, agent)) agents[agent] = 'done'
    }
    if (item.node === 'chain') {
      for (const agent of AGENTS) if (containsAgent(item.detail, agent)) agents[agent] = 'done'
    }
    if (item.node === 'parallel') {
      for (const agent of AGENTS) agents[agent] = 'done'
    }
    if (item.node === 'conflict_check') {
      conflict = 'done'
      const match = item.detail.match(/分歧\s*=\s*(true|false)/i)
      if (match) hasConflict = match[1].toLowerCase() === 'true'
    }
    if (item.node === 'debate') debate = 'done'
    if (item.node === 'report') report = 'done'
    if (item.node === 'reflection') reflection = 'done'
  }

  if (hasConflict === false && debate === 'pending') debate = 'skipped'
  return {
    strategy,
    route,
    agents: skippedAgents(strategy, agents),
    conflict: strategy === 'parallel' ? conflict : 'skipped',
    debate: strategy === 'parallel' ? debate : 'skipped',
    report,
    reflection,
  }
}
