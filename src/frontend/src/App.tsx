import { useEffect, useState } from 'react'
import { getHealth } from './api/health'
import type { HealthResponse } from './types/api'

const NEXT_STEPS = [
  ['M7.1', '同步诊断闭环', '输入问题、POST /diagnose、报告与错误状态'],
  ['M7.2', 'Trace 回放拓扑', 'direct / chain / parallel 固定 fixture'],
  ['M7.3', 'SSE 实时增量', 'progress / complete / error 与同步回退'],
  ['M7.4', 'M5 指标看板', 'ECharts 与真实跑批收益边界'],
  ['M7.5', '端到端验收', '代理联调、截图、响应式与 demo 收口'],
]

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  async function checkHealth() {
    setLoading(true)
    setError('')
    try {
      setHealth(await getHealth())
    } catch (requestError) {
      setHealth(null)
      setError(requestError instanceof Error ? requestError.message : '后端健康检查失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void checkHealth()
  }, [])

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">OM</div>
          <div>
            <strong>OperMind</strong>
            <span>多智能体运维诊断协作系统</span>
          </div>
        </div>
        <span className="phase-chip">M7.0 · FRONTEND FOUNDATION</span>
      </header>

      <main className="foundation-layout">
        <section className="hero-card">
          <span className="eyebrow">OPERATIONS INTELLIGENCE</span>
          <h1>前端工程地基<br /><em>已经就绪。</em></h1>
          <p>本阶段只验证 React、TypeScript、Vite 代理和后端健康检查。诊断输入、Trace、SSE 与图表将在后续小步骤中逐一接入。</p>
          <button className="primary-button" type="button" onClick={() => void checkHealth()} disabled={loading}>
            {loading ? '检查中…' : '重新检查后端'}
          </button>
        </section>

        <section className="health-card">
          <span className="eyebrow">API CONNECTIVITY</span>
          <h2>后端健康检查</h2>
          {health ? (
            <div className="health-success">
              <span className="status-dot" />
              <div><strong>服务可连接</strong><small>{health.mode.toUpperCase()} · {health.model}</small></div>
            </div>
          ) : (
            <div className="health-empty">
              <span className="status-dot offline" />
              <div><strong>{loading ? '正在连接…' : '暂时不可连接'}</strong><small>{error || '等待 /api/health 返回'}</small></div>
            </div>
          )}
          <p className="health-note">开发环境由 Vite 将 <code>/api/*</code> 代理到 FastAPI；前端不读取或展示任何 API Key。</p>
        </section>

        <section className="next-steps-card">
          <div className="section-heading"><span className="eyebrow">EXECUTION GUIDE</span><h2>M7 后续实施步骤</h2></div>
          <div className="step-grid">
            {NEXT_STEPS.map(([id, title, detail]) => (
              <article className="step-card" key={id}>
                <span>{id}</span><strong>{title}</strong><p>{detail}</p>
              </article>
            ))}
          </div>
        </section>
      </main>
      <footer>OperMind · Mock-first · M7.0 仅包含工程地基</footer>
    </div>
  )
}
