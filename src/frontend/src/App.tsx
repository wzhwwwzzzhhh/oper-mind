import { useEffect, useRef, useState } from 'react'
import { diagnose } from './api/diagnosis'
import { getHealth } from './api/health'
import { TracePlayback } from './components/trace/TracePlayback'
import type { DiagnoseResponse, HealthResponse } from './types/api'

const DEMO_CASES = [
  ['慢 SQL', "帮我分析这个SQL：SELECT * FROM orders WHERE status = 'PENDING'"],
  ['复合故障', '系统很慢，经常超时，帮我排查一下'],
  ['大促体检', '明天大促，帮我全面体检一下系统整体健康度'],
] as const

const NEXT_STEPS = [
  ['M7.3', 'SSE 实时增量', 'progress / complete / error 与同步回退'],
  ['M7.4', 'M5 指标看板', 'ECharts 与真实跑批收益边界'],
  ['M7.5', '端到端验收', '代理联调、截图、响应式与 demo 收口'],
]

type RunStatus = 'idle' | 'running' | 'success' | 'error'

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
  const [status, setStatus] = useState<RunStatus>('idle')
  const [error, setError] = useState('')
  const abortRef = useRef<AbortController | null>(null)

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

  useEffect(() => {
    void checkHealth()
    return () => abortRef.current?.abort()
  }, [])

  async function submitDiagnosis(nextQuery = query) {
    const normalized = nextQuery.trim()
    if (!normalized || status === 'running') return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setQuery(normalized)
    setResponse(null)
    setError('')
    setStatus('running')

    try {
      const result = await diagnose(normalized, controller.signal)
      setResponse(result)
      setStatus('success')
    } catch (requestError) {
      if (controller.signal.aborted) return
      setError(requestError instanceof Error ? requestError.message : '诊断请求失败')
      setStatus('error')
    }
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
  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">OM</div>
          <div><strong>OperMind</strong><span>多智能体运维诊断协作系统</span></div>
        </div>
        <span className="phase-chip">M7.2 · TRACE REPLAY</span>
      </header>

      <main className="diagnosis-layout">
        <section className="hero-card">
          <span className="eyebrow">TRACE REPLAY / 02</span>
          <h1>让协作过程<br /><em>可见、可回放。</em></h1>
          <p>当前 Step 在同步诊断闭环之上，使用后端返回的 trace 回放三种路由拓扑。实时 SSE 点亮仍严格后置到 M7.3。</p>
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
          <div className="section-heading"><div><span className="eyebrow">DIAGNOSIS INPUT</span><h2>发起同步诊断</h2></div><span className="step-note">POST /diagnose</span></div>
          <form onSubmit={(event) => { event.preventDefault(); void submitDiagnosis() }}>
            <textarea aria-label="运维问题" value={query} onChange={(event) => setQuery(event.target.value)} disabled={running} rows={4} placeholder="描述 SQL、服务器、日志或复合故障…" />
            <div className="form-footer">
              <div className="demo-buttons"><span>快速场景</span>{DEMO_CASES.map(([label, value]) => <button key={label} type="button" className="demo-chip" onClick={() => setQuery(value)} disabled={running}>{label}</button>)}</div>
              <button className="primary-button" type="submit" disabled={running || !query.trim()}>{running ? <><span className="spinner" /> 诊断中</> : <>开始诊断 <span>→</span></>}</button>
            </div>
          </form>
          {error && <div className="notice notice-error">{error}</div>}
        </section>

        <section className="panel report-panel">
          <div className="section-heading"><div><span className="eyebrow">DIAGNOSIS REPORT</span><h2>最终报告</h2></div>{response && <button type="button" className="text-button" onClick={() => void copyReport()}>复制报告</button>}</div>
          {running ? <div className="report-loading"><span /><span /><span /><span className="short" /></div> : response ? <><div className="report-meta">{reportStats(response)}</div><pre className="report-content">{response.result}</pre></> : <div className="report-empty"><strong>{status === 'error' ? '诊断没有完成' : '报告将在诊断完成后出现'}</strong><span>{status === 'error' ? '请检查后端连接和输入后重试。' : '也可以直接使用下方固定 trace fixture 回放三种协作路径。'}</span></div>}
        </section>

        <TracePlayback response={response} />

        <section className="next-steps-card"><div className="section-heading"><span className="eyebrow">EXECUTION GUIDE</span><h2>下一步</h2></div><div className="step-grid">{NEXT_STEPS.map(([id, title, detail]) => <article className="step-card" key={id}><span>{id}</span><strong>{title}</strong><p>{detail}</p></article>)}</div></section>
      </main>
      <footer>OperMind · Mock-first · M7.2 Trace 回放与三路拓扑</footer>
    </div>
  )
}
