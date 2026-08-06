import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { ReactElement } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { api_v1_client } from '../../api/v1/client'
import { get_service_monitor_history_query, get_service_query, list_service_activities_query } from '../../api/v1/queries'
import {
  read_items,
  read_record,
  resource_optional_string,
  resource_string,
  resource_value,
} from '../workbench/resource-readers'

function kind_label(kind: unknown): { short: string; label: string } {
  const value = String(kind ?? '').toLowerCase()
  if (value.includes('postgres')) return { short: 'PG', label: 'PostgreSQL' }
  if (value.includes('mysql')) return { short: 'my', label: 'MySQL' }
  if (value.includes('redis')) return { short: 'Re', label: 'Redis' }
  if (value.includes('kubernetes') || value.includes('k8s')) return { short: 'K8s', label: 'Kubernetes' }
  return { short: 'Sv', label: value || '服务' }
}

function status_label(value: unknown): string {
  if (value === 'healthy') return '正常'
  if (value === 'unhealthy') return '需关注'
  if (value === 'not_configured') return '未配置'
  if (value === 'unavailable') return '不可用'
  return '未知'
}

function status_class(value: unknown): 'ok' | 'attention' | 'muted' {
  if (value === 'healthy') return 'ok'
  if (value === 'unhealthy') return 'attention'
  return 'muted'
}

function signal_label(value: unknown): string {
  if (value === 'slow_query_detected') return '检测到慢查询'
  if (value === 'no_slow_query_detected') return '未检测到慢查询'
  if (value === 'missing_index_seq_scan_detected') return '发现索引/扫描信号'
  if (value === 'index_and_plan_confirmed') return '索引与执行计划已确认'
  if (value === 'insufficient_data') return '数据不足'
  if (value === 'not_configured') return '未配置'
  if (value === 'unavailable') return '不可用'
  return '暂无信号'
}

function display_number(value: unknown, suffix = ''): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value}${suffix}` : '—'
}

function display_time(value: unknown): string {
  if (typeof value !== 'string' || !value) return '—'
  return value.replace('T', ' ').replace('Z', '').slice(0, 16)
}

function source_label(value: unknown): string {
  if (value === 'available') return '可用'
  if (value === 'unavailable') return '不可用'
  if (value === 'not_configured') return '未配置'
  return '—'
}

function activity_state(value: unknown): string {
  if (value === 'succeeded') return '已完成'
  if (value === 'failed') return '失败'
  if (value === 'running') return '进行中'
  if (value === 'queued') return '排队中'
  if (value === 'cancelled') return '已取消'
  return '—'
}

function monitor_status_label(value: unknown): string {
  if (value === 'available') return '有历史样本'
  if (value === 'not_configured') return '未配置'
  if (value === 'unavailable') return '采样不可用'
  return '暂无历史采样'
}

function monitor_value(value: unknown, suffix = ''): string {
  return typeof value === 'number' && Number.isFinite(value) ? `${value}${suffix}` : '—'
}

/** 单服务详情页：只展示后端真实服务快照，缺失数据保持诚实空态。 */
export function ServiceDetailPage(): ReactElement {
  const navigate = useNavigate()
  const query_client = useQueryClient()
  const { service_id } = useParams<{ service_id: string }>()
  const id = service_id ?? ''
  const service_query = useQuery({ ...get_service_query(id), enabled: Boolean(id) })
  const activities_query = useQuery({ ...list_service_activities_query(id), enabled: Boolean(id) })
  const monitor_query = useQuery({ ...get_service_monitor_history_query(id), enabled: Boolean(id) })
  const [notice, set_notice] = useState<string | null>(null)

  const service_response = service_query.data ? read_record(service_query.data.data) : undefined
  const service = read_record(resource_value(service_response, 'service'))
  const investigations = read_items(resource_value(service, 'supported_investigations'))

  const create_investigation = useMutation({
    mutationFn: () => api_v1_client.create_service_session(id, {}),
    onSuccess: async (response) => {
      const session = read_record(response.data.session)
      const session_id = resource_optional_string(session, 'id')
      await query_client.invalidateQueries({ queryKey: ['api-v1', 'sessions'] })
      if (session_id) {
        const first_investigation = read_record(investigations[0])
        const intent = resource_optional_string(first_investigation, 'id') ?? 'service-investigation'
        navigate(`/workbench/sessions/${encodeURIComponent(session_id)}?intent=${encodeURIComponent(intent)}`)
      } else {
        set_notice('服务会话已创建，但响应缺少会话 ID。')
      }
    },
    onError: () => set_notice('暂时无法创建服务调查，请稍后重试。'),
  })

  const snapshot = read_record(resource_value(service, 'snapshot'))
  const server_metrics = read_record(resource_value(snapshot, 'server_metrics'))
  const database = read_record(resource_value(snapshot, 'database'))
  const kind = kind_label(resource_value(service, 'kind'))
  const availability = resource_value(snapshot, 'availability')
  const activities = activities_query.data ? read_items(activities_query.data.data) : []

  if (service_query.isPending) {
    return <div className="svc-detail-page"><div className="svc-detail-empty">正在读取服务详情…</div></div>
  }

  if (service_query.isError || !service) {
    return (
      <div className="svc-detail-page">
        <button className="svc-detail-back" onClick={() => navigate('/services')} type="button">服务中心</button>
        <div className="svc-detail-empty"><strong>暂时无法读取该服务</strong><span>服务不存在、接口不可用，或当前工作空间没有访问权限。</span></div>
      </div>
    )
  }

  const title = resource_string(service, 'title', '未命名服务')
  const action_boundary = resource_string(service, 'action_boundary', '当前没有可展示的动作边界。')
  const snapshot_mode = resource_string(snapshot, 'mode', '—')
  const snapshot_source = resource_string(server_metrics, 'source_status', '—')

  return (
    <div className="svc-detail-page">
      <div className="svc-detail-breadcrumb">
        <button onClick={() => navigate('/services')} type="button">服务中心</button>
        <span>/</span>
        <strong>{title}</strong>
      </div>

      <section className="svc-detail-hero">
        <div className="svc-detail-hero-copy">
          <div className={`svc-detail-logo ${kind.label.toLowerCase()}`}>{kind.short}</div>
          <div>
            <div className="svc-detail-eyebrow">{kind.label} 服务 <span className={`svc-detail-badge ${status_class(availability)}`}>{status_label(availability)}</span></div>
            <h1>{title}</h1>
            <p>{resource_string(service, 'id', id)} · {snapshot_mode === 'mock' ? '演示快照' : snapshot_mode === 'target' ? '目标快照' : '受控访问'}</p>
          </div>
        </div>
        <div className="svc-detail-actions">
          <button className="svc-detail-button" onClick={() => { void service_query.refetch(); void activities_query.refetch(); void monitor_query.refetch(); set_notice('已请求刷新服务快照。') }} type="button">重新检查</button>
          <button className="svc-detail-button primary" disabled={create_investigation.isPending} onClick={() => create_investigation.mutate()} type="button">{create_investigation.isPending ? '创建中…' : '发起调查'}</button>
        </div>
      </section>

      <div className="svc-detail-meta">
        <span>服务状态 <b className={`text-${status_class(availability)}`}>{status_label(availability)}</b></span>
        <span>最近检查 <b>{display_time(resource_value(snapshot, 'observed_at'))}</b></span>
        <span>数据来源 <b>{source_label(snapshot_source)}</b></span>
        <span>权限边界 <b>只读</b></span>
        <span>快照模式 <b>{snapshot_mode}</b></span>
      </div>

      {notice && <div className="svc-detail-toast" role="status">{notice}<button onClick={() => set_notice(null)} type="button">×</button></div>}

      <div className={`svc-detail-notice ${status_class(availability)}`}>
        <div className="svc-detail-notice-mark">{availability === 'healthy' ? '✓' : '!'}</div>
        <div><strong>{availability === 'healthy' ? '服务运行正常' : availability ? `服务状态：${status_label(availability)}` : '暂无服务快照'}</strong><p>{snapshot ? `性能信号：${signal_label(resource_value(snapshot, 'performance_signal'))}` : '后端没有返回当前快照，页面不展示示例指标。'}</p></div>
        <span>{snapshot ? `观测于 ${display_time(resource_value(snapshot, 'observed_at'))}` : '等待真实数据'}</span>
      </div>

      <section className="svc-detail-section">
        <div className="svc-detail-section-head"><div><h2>当前健康概览</h2><p>只展示服务 API 返回的有限指标，缺失数据以“—”表示。</p></div></div>
        <div className="svc-detail-metrics">
          <article className="svc-detail-metric"><span>服务可用性</span><strong>{status_label(availability)}</strong><small>{snapshot ? `来源：${source_label(resource_value(snapshot, 'availability'))}` : '暂无快照'}</small></article>
          <article className="svc-detail-metric"><span>P50 延迟</span><strong>{display_number(resource_value(server_metrics, 'p50_ms'), ' ms')}</strong><small>最近观测窗口</small></article>
          <article className="svc-detail-metric"><span>P95 延迟</span><strong>{display_number(resource_value(server_metrics, 'p95_ms'), ' ms')}</strong><small>最近观测窗口</small></article>
          <article className="svc-detail-metric"><span>慢查询</span><strong>{display_number(resource_value(server_metrics, 'slow_query_count'), ' 条')}</strong><small>超时 {display_number(resource_value(server_metrics, 'timeout_count'), ' 次')}</small></article>
        </div>
      </section>

      <div className="svc-detail-two-col">
        <section className="svc-detail-card">
          <div className="svc-detail-card-head"><div><h3>运行趋势</h3><p>定时采样 · 每 5 分钟 · 保留最近 24 小时 · 历史记录</p></div></div>
          {monitor_query.isPending && <div className="svc-detail-chart-empty"><strong>正在读取历史采样…</strong></div>}
          {monitor_query.isError && <div className="svc-detail-chart-empty"><strong>暂时无法读取历史采样</strong><p>接口不可用时不展示示例趋势。</p></div>}
          {monitor_query.isSuccess && (() => {
            const history = monitor_query.data.data
            const samples = Array.isArray(history.samples) ? history.samples : []
            const anomalies = samples.filter((item, index) => (item.slow_query_count ?? 0) > 0 || (item.timeout_count ?? 0) > 0 || (index > 0 && item.availability !== samples[index - 1].availability))
            if (samples.length === 0) return <div className="svc-detail-chart-empty"><span>⌁</span><strong>暂无历史采样</strong><p>{monitor_status_label(history.status)}，不会绘制假趋势线。</p></div>
             return <div className="svc-detail-chart"><div className="svc-detail-chart-legend"><span>p95 延迟</span><span>慢查询 / 超时</span></div><div className="svc-detail-chart-track">{samples.map((item) => <div className={`svc-detail-chart-point ${anomalies.includes(item) ? 'anomaly' : ''}`} key={item.id ?? item.observed_at} title={`${display_time(item.observed_at)} · ${monitor_value(item.p95_ms, ' ms')}`}><i style={{ height: `${Math.min(100, Math.max(8, (item.p95_ms ?? 0) / 4))}%` }} /></div>)}</div><div className="svc-detail-chart-axis"><span>{display_time(samples[0].observed_at)}</span><span>{display_time(samples[samples.length - 1].observed_at)}</span></div>{anomalies.length > 0 && <div className="svc-detail-anomalies"><strong>采样点异常</strong>{anomalies.slice(-5).map((item) => <span key={item.id ?? item.observed_at}>{display_time(item.observed_at)} · {(item.slow_query_count ?? 0) > 0 ? `慢查询 ${item.slow_query_count}` : ''}{(item.timeout_count ?? 0) > 0 ? ` 超时 ${item.timeout_count}` : ''}</span>)}</div>}</div>
          })()}
        </section>
        <section className="svc-detail-card">
          <div className="svc-detail-card-head"><div><h3>当前关注</h3><p>由当前快照和活动摘要形成。</p></div></div>
          <div className="svc-detail-attention"><span className={`attention-dot ${status_class(availability)}`} /><div><strong>{snapshot ? signal_label(resource_value(snapshot, 'performance_signal')) : '暂无可确认的运行信号'}</strong><p>{snapshot ? `数据库信号：${signal_label(resource_value(database, 'signal'))}` : '没有返回可用于判断的快照数据。'}</p></div></div>
          <div className="svc-detail-attention"><span className={`attention-dot ${snapshot_source === 'available' ? 'ok' : 'muted'}`} /><div><strong>数据源：{source_label(snapshot_source)}</strong><p>{snapshot ? '指标来源状态由服务端快照提供。' : '请先完成服务连接或监控配置。'}</p></div></div>
        </section>
      </div>

      <section className="svc-detail-section">
        <div className="svc-detail-section-head"><div><h2>服务能力</h2><p>只读能力声明，不代表前端可以直接访问外部服务。</p></div></div>
        <div className="svc-detail-capabilities">
          {investigations.length > 0 ? investigations.map((item, index) => {
            const investigation = read_record(item)
            return <article className="svc-detail-capability" key={resource_string(investigation, 'id', String(index))}><div><span className="capability-mark">✓</span><strong>{resource_string(investigation, 'title', '未命名调查')}</strong></div><p>{resource_string(investigation, 'description', '暂无调查说明。')}</p><small>已启用调查入口</small></article>
          }) : <article className="svc-detail-capability muted"><div><span className="capability-mark">—</span><strong>暂无已启用调查</strong></div><p>当前服务没有返回 supported_investigations。</p><small>未启用</small></article>}
          <article className="svc-detail-capability boundary"><div><span className="capability-mark">◇</span><strong>动作边界</strong></div><p>{action_boundary}</p><small>只读展示</small></article>
        </div>
      </section>

      <section className="svc-detail-section">
        <div className="svc-detail-section-head"><div><h2>最近活动</h2><p>服务关联的调查与闭环摘要。</p></div></div>
        <div className="svc-detail-activity">
          {activities_query.isPending && <div className="svc-detail-inline-empty">正在读取活动…</div>}
          {activities_query.isError && <div className="svc-detail-inline-empty">暂时无法读取活动记录。</div>}
          {activities_query.isSuccess && activities.length === 0 && <div className="svc-detail-inline-empty">当前没有服务活动记录。</div>}
          {activities.map((item, index) => { const activity = read_record(item); return <div className="svc-detail-event" key={resource_string(activity, 'run_id', String(index))}><time>{display_time(resource_value(activity, 'created_at'))}</time><div><strong>{resource_string(activity, 'session_title', '未命名调查')}</strong><p>{resource_string(activity, 'summary', '暂无活动摘要。')}</p></div><b className={resource_value(activity, 'run_status') === 'failed' ? 'warn' : ''}>{activity_state(resource_value(activity, 'run_status'))}</b></div> })}
        </div>
      </section>

      <section className="svc-detail-section">
        <div className="svc-detail-section-head"><div><h2>服务信息</h2><p>服务身份、快照和访问边界。</p></div></div>
        <div className="svc-detail-facts">
          <div><small>服务 ID</small><b>{resource_string(service, 'id', id)}</b></div>
          <div><small>服务类型</small><b>{kind.label}</b></div>
          <div><small>快照模式</small><b>{snapshot_mode}</b></div>
          <div><small>最近观测</small><b>{display_time(resource_value(snapshot, 'observed_at'))}</b></div>
          <div><small>数据库信号</small><b>{signal_label(resource_value(database, 'signal'))}</b></div>
          <div><small>动作边界</small><b>{action_boundary}</b></div>
        </div>
      </section>
    </div>
  )
}

