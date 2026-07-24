import { useEffect, useMemo, useRef, useState } from 'react'
import type { DiagnoseResponse, TraceEvent } from '../../types/api'
import { buildReplaySnapshot, strategyFromResponse, strategyFromTrace, TRACE_FIXTURES, type AgentId, type NodeState } from '../../trace/replay'

interface TracePlaybackProps {
  response: DiagnoseResponse | null
}

const AGENTS: Array<{ id: AgentId; label: string; short: string; color: string }> = [
  { id: 'db', label: '数据库 Agent', short: 'DB', color: 'blue' },
  { id: 'server', label: '服务器 Agent', short: 'SV', color: 'orange' },
  { id: 'log', label: '日志 Agent', short: 'LG', color: 'purple' },
]

function statusText(status: NodeState): string {
  if (status === 'done') return '已完成'
  if (status === 'skipped') return '跳过'
  return '等待'
}

function displayTime(event: TraceEvent): string {
  return new Date(event.timestamp).toLocaleTimeString()
}

export function TracePlayback({ response }: TracePlaybackProps) {
  const [fixtureId, setFixtureId] = useState('parallel')
  const [useResponse, setUseResponse] = useState(true)
  const [visibleCount, setVisibleCount] = useState(0)
  const timerRef = useRef<number | null>(null)

  const fixture = TRACE_FIXTURES.find((item) => item.id === fixtureId) ?? TRACE_FIXTURES[2]
  const hasResponseTrace = Boolean(response?.trace?.length)
  const useResponseTrace = useResponse && hasResponseTrace
  const trace = useResponseTrace ? response?.trace ?? [] : fixture.trace
  const strategy = useResponseTrace
    ? strategyFromResponse(response) || strategyFromTrace(trace)
    : fixture.strategy
  const sourceLabel = useResponseTrace ? '本次同步诊断' : fixture.label
  const snapshot = useMemo(
    () => buildReplaySnapshot(trace, strategy, visibleCount),
    [trace, strategy, visibleCount],
  )

  useEffect(() => {
    setVisibleCount(0)
    if (timerRef.current !== null) window.clearInterval(timerRef.current)
  }, [trace, strategy])

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearInterval(timerRef.current)
  }, [])

  function stepForward() {
    setVisibleCount((count) => Math.min(count + 1, trace.length))
  }

  function replay() {
    if (timerRef.current !== null) window.clearInterval(timerRef.current)
    setVisibleCount(0)
    timerRef.current = window.setInterval(() => {
      setVisibleCount((count) => {
        const next = count + 1
        if (next >= trace.length && timerRef.current !== null) {
          window.clearInterval(timerRef.current)
          timerRef.current = null
        }
        return Math.min(next, trace.length)
      })
    }, 520)
  }

  return (
    <section className="panel trace-panel">
      <div className="section-heading">
        <div><span className="eyebrow">TRACE REPLAY</span><h2>诊断链路回放</h2></div>
        <span className={`strategy-badge strategy-${strategy || 'unknown'}`}>{strategy || 'unknown'}</span>
      </div>
      <p className="trace-caption">过程只由后端 trace 驱动。当前来源：<strong>{sourceLabel}</strong></p>

      <div className="trace-source-switch">
        {hasResponseTrace ? <button className={useResponse ? 'active' : ''} type="button" onClick={() => setUseResponse(true)}>本次诊断</button> : null}
        {TRACE_FIXTURES.map((item) => <button key={item.id} className={!useResponse && fixtureId === item.id ? 'active' : ''} type="button" onClick={() => { setUseResponse(false); setFixtureId(item.id) }}>{item.label}</button>)}
      </div>

      <div className="trace-controls">
        <button type="button" className="text-button" onClick={replay}>从头播放</button>
        <button type="button" className="text-button" onClick={stepForward} disabled={visibleCount >= trace.length}>下一步</button>
        <span>{visibleCount} / {trace.length} 个事件</span>
      </div>

      <div className="trace-flow">
        <div className={`flow-node ${snapshot.route}`}><span>ROUTE</span><strong>Coordinator</strong><small>{statusText(snapshot.route)}</small></div>
        <div className="flow-link" />
        <div className={`agent-cluster strategy-${strategy}`}>
          {AGENTS.map((agent) => <div className={`agent-node ${agent.color} ${snapshot.agents[agent.id]}`} key={agent.id}><i>{agent.short}</i><div><strong>{agent.label}</strong><small>{statusText(snapshot.agents[agent.id])}</small></div></div>)}
        </div>
        <div className="flow-link" />
        <div className="quality-cluster">
          <div className={`quality-node ${snapshot.conflict}`}><strong>Conflict</strong><small>{statusText(snapshot.conflict)}</small></div>
          <div className={`quality-node debate ${snapshot.debate}`}><strong>Debate</strong><small>{statusText(snapshot.debate)}</small></div>
          <div className={`quality-node reflection ${snapshot.reflection}`}><strong>Reflection</strong><small>{statusText(snapshot.reflection)}</small></div>
        </div>
        <div className="flow-link" />
        <div className={`flow-node report ${snapshot.report}`}><span>OUTPUT</span><strong>报告</strong><small>{statusText(snapshot.report)}</small></div>
      </div>

      <div className="trace-events">
        {trace.slice(0, visibleCount).map((event, index) => <div className="trace-event" key={`${event.timestamp}-${index}`}><span>{displayTime(event)}</span><b>{event.type}</b><p>{event.detail}</p></div>)}
        {visibleCount === 0 ? <div className="trace-empty">点击“下一步”或“从头播放”查看由 trace 驱动的拓扑变化。</div> : null}
      </div>
    </section>
  )
}
