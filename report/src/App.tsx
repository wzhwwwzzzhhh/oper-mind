import { useEffect, useRef, useState } from 'react'
import { diagnose } from './api/diagnosis'
import { subscribeDiagnosisStream } from './api/stream'
import { getHealth } from './api/health'
import { TracePlayback } from './components/trace/TracePlayback'
import { MetricsDashboard } from './components/charts/MetricsDashboard'
import type { DiagnoseResponse, HealthResponse, TraceEvent } from './types/api'

const DEMO_CASES = [
  ['慢 SQL', "帮我分析这个SQL：SELECT * FROM orders WHERE status = 'PENDING'"],
  ['复合故障', '系统很慢，经常超时，帮我排查一下'],
  ['大促体检', '明天大促，帮我全面体检一下系统整体健康度'],
] as const

const NEXT_STEPS = [
  ['M7.5', '端到端验收', '代理联调、截图、响应式与 demo 收口'],
]

type RunStatus = 'idle' | 'running' | 'success' | 'error'
type DiagnosisMode = 'stream' | 'fallback'

function reportStats(response: DiagnoseResponse): string {
  const traceCount = response.trace?.length ?? 0
  const thinkingCount = response.thinking?.length ?? 0
  return `${response.strategy || 'unknown'} · ${traceCount} 条 trace · ${thinkingCount} 条思考摘要`
}

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthError, setHealthError] = useState('')
  const [query, setQuery] = useState<string>(DEMO_CASES[2][1])
  const [response, setResponse] = useState<DiagnoseResponse | null>(null)
  const [liveTrace, setLiveTrace] = useState<TraceEvent[]>([])
  const [status, setStatus] = useState<RunStatus>('idle')
  const [mode, setMode] = useState<DiagnosisMode>('stream')
  const [error, setError] = useState('')
  const abortRef = useRef<AbortController | null>(null)
  const closeStreamRef = useRef<(() => void) | null>(null)
  const runIdRef = useRef(0)
  const fallbackStartedRef = useRef(false)

  async function checkHealth() {
    setHealthLoading(true)
    setHealthError('')
    try {
      setHealth(await getHealth())
    } catch (requestError) {
      setHealth(null)
      setHealthError(requestError instanceof Error ? requestError.message : '后端健康检查失败')
    } finally {
      setHealthLoading(false)
    }
  }

  function cancelActiveRun(): void {
    runIdRef.current += 1
    closeStreamRef.current?.()
    closeStreamRef.current = null
    abortRef.current?.abort()
    abortRef.current = null
  }

  useEffect(() => {
    void checkHealth()
    return cancelActiveRun
  }, [])

  async function runSyncFallback(normalized: string, runId: number, message?: string): Promise<void> {
    if (fallbackStartedRef.current) return
    fallbackStartedRef.current = true
    closeStreamRef.current?.()
    closeStreamRef.current = null
    const controller = new AbortController()
    abortRef.current = controller
    setMode('fallback')
    if (message) setError(message)

    try {
      const result = await diagnose(normalized, controller.signal)
      if (runId !== runIdRef.current) return
      setResponse(result)
      setLiveTrace(result.trace ?? [])
      setStatus('success')
    } catch (requestError) {
      if (controller.signal.aborted || runId !== runIdRef.current) return
      setError(requestError instanceof Error ? requestError.message : '同步诊断请求失败')
      setStatus('error')
    }
  }

  function submitDiagnosis(nextQuery = query): void {
    const normalized = nextQuery.trim()
    if (!normalized || status === 'running') return

    cancelActiveRun()
    const runId = runIdRef.current + 1
    runIdRef.current = runId
    setQuery(normalized)
    setResponse(null)
    setLiveTrace([])
    fallbackStartedRef.current = false
    setError('')
    setMode('stream')
    setStatus('running')

    closeStreamRef.current = subscribeDiagnosisStream(normalized, {
      onProgress: (event) => {
        if (runId !== runIdRef.current) return
        setLiveTrace((trace) => [...trace, event])
      },
      onComplete: (event) => {
        if (runId !== runIdRef.current) return
        closeStreamRef.current = null
        setResponse({ result: event.result, strategy: event.strategy, trace: event.trace })
        setLiveTrace(event.trace)
        setStatus('success')
      },
      onError: (streamError) => {
        if (runId !== runIdRef.current) return
        void runSyncFallback(normalized, runId, `实时流不可用，已切换同步诊断：${streamError.message}`)
      },
    })
  }

  function switchToSync(): void {
    if (status !== 'running') return
    const normalized = query.trim()
    if (!normalized) return
    void runSyncFallback(normalized, runIdRef.current, '已结束实时流，正在使用同步诊断完成本次请求。')
  }

  async function copyReport() {
    if (!response?.result) return
    try {
      await navigator.clipboard.writeText(response.result)
    } catch {
      setError('复制失败，请手动选择报告文本')
    }
  }

  const running = status === 'running'
  const modeLabel = mode === 'stream' ? 'SSE /diagnose/stream' : '同步降级 POST /diagnose'
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">OM</div>
          <div><strong>OperMind</strong><span>多智能体运维诊断协作系统</span></div>
        </div>
        <span className="phase-chip">M7.4 · EVIDENCE DASHBOARD</span>
      </header>

      <main className="diagnosis-layout">
        <section className="hero-card">
          <span className="eyebrow">EVIDENCE DASHBOARD / 04</span>
          <h1>让协作价值<br /><em>可量化、可追溯。</em></h1>
          <p>在实时诊断闭环之外，展示 M5 两臂真实跑批的质量、成本和分组收益边界；图表不替代统计显著性检验。</p>
        </section>

        <section className="health-card">
          <div className="card-label-row"><span className="eyebrow">API CONNECTIVITY</span><button type="button" className="text-button" onClick={() => void checkHealth()} disabled={healthLoading}>刷新</button></div>
          <h2>后端状态</h2>
          {health ? (
            <div className="health-success"><span className="status-dot" /><div><strong>服务可连接</strong><small>{health.mode.toUpperCase()} · {health.model}</small></div></div>
          ) : (
            <div className="health-empty"><span className="status-dot offline" /><div><strong>{healthLoading ? '正在连接…' : '暂时不可连接'}</strong><small>{healthError || '等待 /api/health 返回'}</small></div></div>
          )}
        </section>

        <section className="panel query-panel">
          <div className="section-heading"><div><span className="eyebrow">DIAGNOSIS INPUT</span><h2>发起实时诊断</h2></div><span className="step-note">{modeLabel}</span></div>
          <form onSubmit={(event) => { event.preventDefault(); submitDiagnosis() }}>
            <textarea aria-label="运维问题" value={query} onChange={(event) => setQuery(event.target.value)} disabled={running} rows={4} placeholder="描述 SQL、服务器、日志或复合故障…" />
            <div className="form-footer">
              <div className="demo-buttons"><span>快速场景</span>{DEMO_CASES.map(([label, value]) => <button key={label} type="button" className="demo-chip" onClick={() => setQuery(value)} disabled={running}>{label}</button>)}</div>
              <div className="diagnosis-actions">
                {running ? <button type="button" className="text-button stream-fallback-button" onClick={switchToSync}>改用同步完成</button> : null}
                <button className="primary-button" type="submit" disabled={running || !query.trim()}>{running ? <><span className="spinner" /> 诊断中</> : <>开始诊断 <span>→</span></>}</button>
              </div>
            </div>
          </form>
          {error && <div className="notice notice-error">{error}</div>}
        </section>

        <section className="panel report-panel">
          <div className="section-heading"><div><span className="eyebrow">DIAGNOSIS REPORT</span><h2>最终报告</h2></div>{response && <button type="button" className="text-button" onClick={() => void copyReport()}>复制报告</button>}</div>
          {running ? <div className="report-loading"><span /><span /><span /><span className="short" /></div> : response ? <><div className="report-meta">{reportStats(response)}</div><pre className="report-content">{response.result}</pre></> : <div className="report-empty"><strong>{status === 'error' ? '诊断没有完成' : '报告将在实时流完成后出现'}</strong><span>{status === 'error' ? '请检查后端连接后重试。' : '实时 trace 会在下方逐步点亮；流失败时会自动切换同步诊断。'}</span></div>}
        </section>

        <TracePlayback response={response} liveTrace={liveTrace} isStreaming={running && mode === 'stream'} isDiagnosticRunning={running} />

        <MetricsDashboard />

        <section className="next-steps-card"><div className="section-heading"><span className="eyebrow">EXECUTION GUIDE</span><h2>下一步</h2></div><div className="step-grid">{NEXT_STEPS.map(([id, title, detail]) => <article className="step-card" key={id}><span>{id}</span><strong>{title}</strong><p>{detail}</p></article>)}</div></section>
      </main>
      <footer>OperMind · Mock-first · M7.4 M5 指标看板（ECharts）</footer>
    </div>
  )
}
