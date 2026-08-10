import { useQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { useNavigate } from 'react-router-dom'

import { get_monitor_overview_query } from '../../api/v1/queries'
import { Icon } from '../shell/Icon'

function kind_label(kind: string): { short: string; label: string } {
  const value = kind.toLowerCase()
  if (value.includes('postgres')) return { short: 'PG', label: 'PostgreSQL' }
  if (value.includes('mysql')) return { short: 'my', label: 'MySQL' }
  if (value.includes('redis')) return { short: 'Re', label: 'Redis' }
  if (value.includes('kubernetes') || value.includes('k8s')) return { short: 'K8s', label: 'Kubernetes' }
  return { short: 'Sv', label: value || '服务' }
}

function connection_label(status: string): string {
  if (status === 'available') return '可用'
  if (status === 'unavailable') return '不可用'
  if (status === 'not_configured') return '未配置'
  return '暂无历史采样'
}

function connection_class(status: string): 'ok' | 'attention' | 'muted' {
  if (status === 'available') return 'ok'
  if (status === 'unavailable' || status === 'not_configured') return 'attention'
  return 'muted'
}

function availability_text(value: string): string {
  if (value === 'healthy') return '正常'
  if (value === 'unhealthy') return '需关注'
  if (value === 'not_configured') return '未配置'
  return '不可用'
}

function display_number(value: number | null | undefined, suffix = ''): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value}${suffix}` : '—'
}

function display_bytes(value: number | null | undefined): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  if (value >= 1048576) return `${(value / 1048576).toFixed(1)} MB`
  return `${value} B`
}

function display_time(value: string | null | undefined): string {
  if (!value) return '—'
  return value.replace('T', ' ').replace('Z', '').slice(0, 16)
}

function is_redis(kind: string): boolean {
  return kind.toLowerCase().includes('redis')
}

/** 采样点的性能信号 → 中文；与服务详情页保持同一套说法。 */
function signal_label(value: string | null | undefined): string {
  if (value === 'slow_query_detected') return '检测到慢查询'
  if (value === 'no_slow_query_detected') return '未检测到慢查询'
  if (value === 'missing_index_seq_scan_detected') return '发现索引/扫描信号'
  if (value === 'index_and_plan_confirmed') return '索引与执行计划已确认'
  if (value === 'insufficient_data') return '数据不足'
  if (value === 'not_configured') return '未配置'
  if (value === 'unavailable') return '不可用'
  return '暂无信号'
}

/** 服务监控概览页：聚合所有已接入服务的定时采样概览，只读历史记录，不伪造实时监控。 */
export function MonitoringOverviewPage(): ReactElement {
  const navigate = useNavigate()
  const overview_query = useQuery({ ...get_monitor_overview_query() })
  const data = overview_query.data?.data
  const items = data?.items ?? []
  const interval_minutes = Math.round((data?.sample_interval_seconds ?? 300) / 60)
  const retention_hours = data?.retention_hours ?? 24

  return (
    <div className="svc-page">
      <div className="breadcrumb">
        <span>会话工作台</span>
        <span>/</span>
        <strong>服务监控</strong>
      </div>

      <section className="page-head">
        <div>
          <div className="eyebrow">Service monitoring</div>
          <h1>服务监控</h1>
          <p>聚合所有已接入服务的定时采样概览，帮助快速判断当前哪些服务出现异常。</p>
        </div>
        <div className="head-actions">
          <button className="btn" disabled={overview_query.isFetching} onClick={() => void overview_query.refetch()} type="button">
            <Icon name="refresh" size={13} />
            {overview_query.isFetching ? '读取中…' : '刷新状态'}
          </button>
        </div>
      </section>

      <div className="monitor-honesty-strip">
        数据来源：定时采样 · 每 {interval_minutes} 分钟 · 保留最近 {retention_hours} 小时 · 历史记录
      </div>

      <section className="section">
        <div className="section-head">
          <h2>监控概览</h2>
          <div className="service-batch-actions">
            <span>异常标记仅为历史采样点的异常信号，不代表外部通知已触发</span>
          </div>
        </div>

        {overview_query.isPending && <div className="svc-empty">正在读取监控概览…</div>}
        {overview_query.isError && (
          <div className="svc-empty">
            <strong>暂时无法读取监控概览</strong>
            <p>接口不可用时不展示示例数据，请稍后重试。</p>
            <button className="btn" onClick={() => void overview_query.refetch()} type="button">重试</button>
          </div>
        )}

        {overview_query.isSuccess && items.length === 0 && (
          <div className="svc-empty">
            当前还没有已接入服务，暂无监控概览。服务接入能力将在后续工作包提供。
          </div>
        )}

        {items.length > 0 && (
          <div className="monitor-table">
            <div className="monitor-table-head">
              <span>服务</span>
              <span>类型 / 采样信号</span>
              <span>连接状态</span>
              <span>最新延迟</span>
              <span>慢查询 / 超时</span>
              <span>异常标记</span>
              <span>主机指标摘要</span>
              {/* 末列表头留空：下面每行是"查看详情"提示，表头再写一遍是重复。 */}
              <span />
            </div>
            {items.map((item) => {
              const info = kind_label(item.kind)
              const is_redis_service = is_redis(item.kind)
              const latest = item.latest_sample
              const anomaly = (item.trend_summary?.anomaly_sample_count ?? 0) > 0
              return (
                <button
                  className="monitor-row"
                  key={item.service_id}
                  onClick={() => navigate(`/services/${encodeURIComponent(item.service_id)}`)}
                  type="button"
                >
                  <div className="monitor-service">
                    <div className={`service-logo ${info.short.toLowerCase()}`}>{info.short}</div>
                    <div className="service-name">
                      <strong>{item.title}</strong>
                      <span>{item.service_id}</span>
                    </div>
                  </div>
                  <div className="type">
                    {info.label}
                    <small>{signal_label(latest?.performance_signal)}</small>
                  </div>
                  <div>
                    <span className={`state ${connection_class(item.connection_status)}`}>
                      {connection_label(item.connection_status)}
                    </span>
                    <small>{availability_text(item.availability)}</small>
                  </div>
                  <div className="fact">
                    <strong>{is_redis_service
                      ? display_bytes(latest?.memory_bytes)
                      : display_number(latest?.p95_ms, ' ms')}</strong>
                    <span>{is_redis_service ? '内存' : `P95 · ${display_time(latest?.observed_at)}`}</span>
                  </div>
                  <div className="fact">
                    <strong>{is_redis_service
                      ? display_number(latest?.slowlog_count, ' 条')
                      : `${display_number(latest?.slow_query_count, ' 条')} · ${display_number(latest?.timeout_count, ' 次')}`}</strong>
                    <span>{is_redis_service ? 'SLOWLOG' : '慢查询 · 超时'}</span>
                  </div>
                  <div>
                    {anomaly
                      ? <span className="monitor-anomaly">采样点异常</span>
                      : <span className="monitor-normal">正常</span>}
                    <small>{item.trend_summary?.sample_count ?? 0} 个采样点</small>
                  </div>
                  <div className="fact">
                    <strong>{display_number(latest?.host_cpu_percent, '%')} / {display_number(latest?.host_memory_percent, '%')} / {display_number(latest?.host_disk_used_percent, '%')}</strong>
                    <span>后端所在主机 · 单主机采集 · {display_time(latest?.observed_at)}</span>
                  </div>
                  <span className="monitor-detail-cue">
                    查看详情
                    <Icon name="chevron-right" size={12} />
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
