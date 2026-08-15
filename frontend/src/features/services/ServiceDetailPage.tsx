import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import type { ReactElement } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { api_v1_client, type MonitorSampleResource, type MonitorThresholdConfigResource } from '../../api/v1/client'
import {
  api_v1_query_keys,
  get_service_monitor_history_query,
  get_service_monitor_thresholds_query,
  get_service_query,
  list_service_activities_query,
} from '../../api/v1/queries'
import { Icon } from '../shell/Icon'
import type { IconName } from '../shell/Icon'
import {
  read_array,
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

/** 状态标记图标：未知不借用告警图标，落到"缺数据"的横杠上。 */
function notice_mark_icon(value: unknown): IconName {
  if (value === 'healthy') return 'check'
  if (value === 'unhealthy') return 'alert'
  return 'minus'
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

function display_bytes(value: unknown): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  if (value >= 1048576) return `${(value / 1048576).toFixed(1)} MB`
  return `${value} B`
}

function is_redis_kind(kind: unknown): boolean {
  return String(kind ?? '').toLowerCase().includes('redis')
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

function host_trend_track(label: string, samples: unknown[], field: string, key_prefix: string, suffix: string): ReactElement | null {
  const points = samples.filter((item) => typeof resource_value(item, field) === 'number')
  if (points.length === 0) return null
  return (
    <div className="svc-detail-chart">
      <div className="svc-detail-chart-legend"><span>{label}</span></div>
      <div className="svc-detail-chart-track">{points.map((item) => { const value = resource_value(item, field) as number; const bar = Math.min(100, Math.max(4, value)); return <div className="svc-detail-chart-point" key={`${key_prefix}-${resource_value(item, 'id') ?? resource_value(item, 'observed_at')}`} title={`${display_time(resource_value(item, 'observed_at'))} · ${label} ${monitor_value(value, suffix)}`}><i style={{ height: `${bar}%` }} /></div> })}</div>
      <div className="svc-detail-chart-axis"><span>{display_time(resource_value(points[0], 'observed_at'))}</span><span>{display_time(resource_value(points[points.length - 1], 'observed_at'))}</span></div>
    </div>
  )
}

type ThresholdMetricField = 'slow_query_count_threshold' | 'timeout_count_threshold' | 'slowlog_count_threshold'

const THRESHOLD_METRIC_FIELDS: ReadonlyArray<{ field: ThresholdMetricField; label: string; hint: string }> = [
  { field: 'slow_query_count_threshold', label: '慢查询计数', hint: 'PostgreSQL 慢查询采样计数' },
  { field: 'timeout_count_threshold', label: '超时计数', hint: 'PostgreSQL 查询超时采样计数' },
  { field: 'slowlog_count_threshold', label: '慢日志计数', hint: 'Redis 慢日志采样计数' },
]

function threshold_window_label(minutes: number): string {
  if (minutes === 0) return '仅当前采样点（出现即异常）'
  return `${minutes} 分钟`
}

function windowed_metric_sums(
  samples: MonitorSampleResource[],
  index: number,
  window_minutes: number,
): { slow_sum: number; timeout_sum: number; slowlog_sum: number } {
  /** §2.3 窗口聚合的前端实现：与后端 `_windowed_metric_sums` 同一规则（含两端、window=0 只含自身、null 计 0）。 */
  const observed_at = Date.parse(samples[index].observed_at)
  const start = observed_at - window_minutes * 60 * 1000
  let slow_sum = 0
  let timeout_sum = 0
  let slowlog_sum = 0
  for (const candidate of samples) {
    const candidate_at = Date.parse(candidate.observed_at)
    if (candidate_at < start) continue
    if (candidate_at > observed_at) break
    slow_sum += candidate.slow_query_count ?? 0
    timeout_sum += candidate.timeout_count ?? 0
    slowlog_sum += candidate.slowlog_count ?? 0
  }
  return { slow_sum, timeout_sum, slowlog_sum }
}

function is_anomalous_sample(
  samples: MonitorSampleResource[],
  index: number,
  config: MonitorThresholdConfigResource,
): boolean {
  /** §2.3 判定契约的前端实现：与后端 `_trend_summary` 同一规则（首样本不判可用性异常、相邻既有样本比较）。 */
  const { slow_sum, timeout_sum, slowlog_sum } = windowed_metric_sums(samples, index, config.window_minutes)
  const has_metric = (
    (config.slow_query_count_threshold !== null && slow_sum >= config.slow_query_count_threshold)
    || (config.timeout_count_threshold !== null && timeout_sum >= config.timeout_count_threshold)
    || (config.slowlog_count_threshold !== null && slowlog_sum >= config.slowlog_count_threshold)
  )
  const availability_changed = (
    config.count_availability_change
    && index > 0
    && samples[index].availability !== samples[index - 1].availability
  )
  return has_metric || availability_changed
}

function anomaly_reasons(
  samples: MonitorSampleResource[],
  index: number,
  config: MonitorThresholdConfigResource,
): string[] {
  /** 触发当前采样点异常的指标原因列表（窗口内计数和 ≥ 阈值 / 可用性变化）。 */
  const { slow_sum, timeout_sum, slowlog_sum } = windowed_metric_sums(samples, index, config.window_minutes)
  const reasons: string[] = []
  if (config.slow_query_count_threshold !== null && slow_sum >= config.slow_query_count_threshold) {
    reasons.push(`慢查询 ${slow_sum}`)
  }
  if (config.timeout_count_threshold !== null && timeout_sum >= config.timeout_count_threshold) {
    reasons.push(`超时 ${timeout_sum}`)
  }
  if (config.slowlog_count_threshold !== null && slowlog_sum >= config.slowlog_count_threshold) {
    reasons.push(`慢日志 ${slowlog_sum}`)
  }
  if (
    config.count_availability_change
    && index > 0
    && samples[index].availability !== samples[index - 1].availability
  ) {
    reasons.push('可用性变化')
  }
  return reasons
}

/** P8 监控阈值配置区：只读回显当前生效规则 + 可编辑保存，来源诚实标注（内置默认/已配置）。 */
function ThresholdConfigCard({ service_id }: { service_id: string }): ReactElement {
  const query_client = useQueryClient()
  const thresholds_query = useQuery({
    ...get_service_monitor_thresholds_query(service_id),
    enabled: Boolean(service_id),
  })
  const [draft, set_draft] = useState<MonitorThresholdConfigResource | null>(null)
  const [error_message, set_error_message] = useState<string | null>(null)
  const [saved_notice, set_saved_notice] = useState<boolean>(false)

  useEffect(() => {
    if (draft === null && thresholds_query.data) {
      set_draft(thresholds_query.data.data.config)
    }
  }, [draft, thresholds_query.data])

  const save_thresholds = useMutation({
    mutationFn: (config: MonitorThresholdConfigResource) =>
      api_v1_client.update_service_monitor_thresholds(service_id, config),
    onSuccess: async () => {
      await query_client.invalidateQueries({ queryKey: api_v1_query_keys.service_monitor_thresholds(service_id) })
      set_error_message(null)
      set_saved_notice(true)
    },
    onError: (error) => {
      set_error_message(error instanceof Error ? error.message : '保存失败，请稍后重试。')
      set_saved_notice(false)
    },
  })

  const configured = thresholds_query.data?.data.source === 'configured'
  const source_note = configured
    ? '以下为保存后的生效规则，保存即生效。'
    : '未配置阈值，当前使用内置默认规则（出现即异常）。'

  const set_metric_enabled = (field: ThresholdMetricField, enabled: boolean) => {
    set_draft((current) => (current ? { ...current, [field]: enabled ? 1 : null } : current))
  }
  const set_metric_threshold = (field: ThresholdMetricField, raw: string) => {
    // 空输入 = 不关注该指标（与勾选开关语义一致）；非法数字回退 0 由后端 422 兜底如实提示。
    if (raw === '') {
      set_draft((current) => (current ? { ...current, [field]: null } : current))
      return
    }
    const parsed = Number(raw)
    set_draft((current) => (current ? { ...current, [field]: Number.isFinite(parsed) ? parsed : 0 } : current))
  }

  return (
    <section className="svc-detail-section">
      <div className="svc-detail-section-head">
        <div><h2>监控阈值</h2><p>采样点异常判定规则 · 只影响异常标记，采样与保留策略不变</p></div>
        {thresholds_query.isSuccess && (
          <span className={`svc-detail-badge ${configured ? 'ok' : 'muted'}`}>{configured ? '已配置' : '内置默认'}</span>
        )}
      </div>
      {thresholds_query.isPending && <div className="svc-detail-inline-empty">正在读取监控阈值配置…</div>}
      {thresholds_query.isError && (
        <div className="svc-detail-inline-empty"><strong>暂时无法读取监控阈值配置</strong><p>接口不可用时不展示示例规则。</p></div>
      )}
      {thresholds_query.isSuccess && draft && (
        <div className="svc-detail-thresholds">
          <p className="svc-detail-thresholds-note">{source_note}</p>
          {THRESHOLD_METRIC_FIELDS.map(({ field, label, hint }) => {
            const enabled = draft[field] !== null
            return (
              <div className="svc-detail-threshold-row" key={field}>
                <label className="svc-detail-threshold-metric">
                  <input type="checkbox" checked={enabled} onChange={(event) => set_metric_enabled(field, event.target.checked)} />
                  <span><strong>{label}</strong><small>{hint}</small></span>
                </label>
                <label className="svc-detail-threshold-value">
                  <span>阈值</span>
                  <input type="number" min={0} step={1} value={draft[field] ?? 0} disabled={!enabled} onChange={(event) => set_metric_threshold(field, event.target.value)} />
                </label>
              </div>
            )
          })}
          <div className="svc-detail-threshold-row">
            <label className="svc-detail-threshold-metric">
              <span><strong>判定窗口</strong><small>窗口内关注指标计数之和 ≥ 阈值时，该采样点计为异常</small></span>
            </label>
            <label className="svc-detail-threshold-value">
              <span>窗口</span>
              <select
                value={draft.window_minutes}
                onChange={(event) => set_draft((current) => (current ? { ...current, window_minutes: Number(event.target.value) } : current))}
              >
                {(() => {
                  const presets = [0, 5, 10, 15, 30]
                  const options = presets.includes(draft.window_minutes) ? presets : [draft.window_minutes, ...presets]
                  return options.map((minutes) => <option value={minutes} key={minutes}>{threshold_window_label(minutes)}</option>)
                })()}
              </select>
            </label>
          </div>
          <div className="svc-detail-threshold-row">
            <label className="svc-detail-threshold-metric">
              <input type="checkbox" checked={draft.count_availability_change} onChange={(event) => set_draft((current) => (current ? { ...current, count_availability_change: event.target.checked } : current))} />
              <span><strong>可用性变化计为异常</strong><small>服务状态在相邻采样点间变化时，该采样点计为异常</small></span>
            </label>
            <div className="svc-detail-threshold-value"><span /></div>
          </div>
          <div className="svc-detail-threshold-actions">
            <button className="svc-detail-button primary" disabled={save_thresholds.isPending} onClick={() => { if (draft) save_thresholds.mutate(draft) }} type="button">{save_thresholds.isPending ? '保存中…' : '保存并生效'}</button>
            {saved_notice && <span className="svc-detail-threshold-saved">已保存，概览与趋势按新规则计算。</span>}
          </div>
          {error_message && (
            <div className="svc-detail-toast" role="alert">
              {error_message}
              <button aria-label="关闭提示" onClick={() => set_error_message(null)} type="button"><Icon name="x" size={13} /></button>
            </div>
          )}
        </div>
      )}
    </section>
  )
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
  const thresholds_query = useQuery({ ...get_service_monitor_thresholds_query(id), enabled: Boolean(id) })
  const [notice, set_notice] = useState<string | null>(null)

  const service_response = service_query.data ? read_record(service_query.data.data) : undefined
  const service = read_record(resource_value(service_response, 'service'))
  const investigations = read_array(resource_value(service, 'supported_investigations'))

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
  const is_redis = is_redis_kind(resource_value(service, 'kind'))
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
          <button className="svc-detail-button primary" disabled={investigations.length === 0 || create_investigation.isPending} onClick={() => create_investigation.mutate()} type="button">{create_investigation.isPending ? '创建中…' : investigations.length === 0 ? '调查未启用' : '发起调查'}</button>
        </div>
      </section>

      <div className="svc-detail-meta">
        <span>服务状态 <b className={`text-${status_class(availability)}`}>{status_label(availability)}</b></span>
        <span>最近检查 <b>{display_time(resource_value(snapshot, 'observed_at'))}</b></span>
        <span>数据来源 <b>{source_label(snapshot_source)}</b></span>
        <span>权限边界 <b>只读</b></span>
        <span>快照模式 <b>{snapshot_mode}</b></span>
      </div>

      {notice && (
        <div className="svc-detail-toast" role="status">
          {notice}
          <button aria-label="关闭提示" onClick={() => set_notice(null)} type="button"><Icon name="x" size={13} /></button>
        </div>
      )}

      <div className={`svc-detail-notice ${status_class(availability)}`}>
        <div className="svc-detail-notice-mark">
          <Icon name={notice_mark_icon(availability)} size={13} />
        </div>
        <div><strong>{availability === 'healthy' ? '服务运行正常' : availability ? `服务状态：${status_label(availability)}` : '暂无服务快照'}</strong><p>{snapshot ? `性能信号：${signal_label(resource_value(snapshot, 'performance_signal'))}` : '后端没有返回当前快照，页面不展示示例指标。'}</p></div>
        <span>{snapshot ? `观测于 ${display_time(resource_value(snapshot, 'observed_at'))}` : '等待真实数据'}</span>
      </div>

      <section className="svc-detail-section">
        <div className="svc-detail-section-head"><div><h2>当前健康概览</h2><p>只展示服务 API 返回的有限指标，缺失数据以“—”表示。</p></div></div>
        <div className="svc-detail-metrics">
          <article className="svc-detail-metric"><span>服务可用性</span><strong>{status_label(availability)}</strong><small>{snapshot ? `来源：${source_label(resource_value(snapshot, 'availability'))}` : '暂无快照'}</small></article>
          {is_redis ? (
            <>
              <article className="svc-detail-metric"><span>内存占用</span><strong>{display_bytes(resource_value(server_metrics, 'memory_bytes'))}</strong><small>used_memory</small></article>
              <article className="svc-detail-metric"><span>客户端连接</span><strong>{display_number(resource_value(server_metrics, 'client_connections'), ' 个')}</strong><small>CLIENT LIST</small></article>
              <article className="svc-detail-metric"><span>慢日志</span><strong>{display_number(resource_value(server_metrics, 'slowlog_count'), ' 条')}</strong><small>SLOWLOG LEN</small></article>
            </>
          ) : (
            <>
              <article className="svc-detail-metric"><span>P50 延迟</span><strong>{display_number(resource_value(server_metrics, 'p50_ms'), ' ms')}</strong><small>最近观测窗口</small></article>
              <article className="svc-detail-metric"><span>P95 延迟</span><strong>{display_number(resource_value(server_metrics, 'p95_ms'), ' ms')}</strong><small>最近观测窗口</small></article>
              <article className="svc-detail-metric"><span>慢查询</span><strong>{display_number(resource_value(server_metrics, 'slow_query_count'), ' 条')}</strong><small>超时 {display_number(resource_value(server_metrics, 'timeout_count'), ' 次')}</small></article>
            </>
          )}
        </div>
      </section>

      <section className="svc-detail-section">
        <div className="svc-detail-section-head"><div><h2>主机指标</h2><p>后端所在主机 · 单主机采集 · 只读本机指标，不代表服务所在远端主机。</p></div></div>
        {(() => {
          const host_metrics = read_record(resource_value(service, 'host_metrics'))
          if (!resource_value(service, 'host_metrics')) {
            return <div className="svc-detail-inline-empty">后端未返回主机指标，不展示示例数据。</div>
          }
          const host_status = resource_string(host_metrics, 'source_status', 'unavailable')
          const host_mode = resource_string(host_metrics, 'mode', 'target')
          const host_source_label = host_mode === 'mock' ? '演示场景' : '真实采集'
          if (host_status === 'unavailable') {
            return <div className="svc-detail-inline-empty"><strong>主机指标不可用</strong><p>psutil 采集不可用，页面不伪造数值。</p></div>
          }
          const processes = read_array(resource_value(host_metrics, 'abnormal_processes'))
          return (
            <div>
              <div className="svc-detail-metrics">
                <article className="svc-detail-metric"><span>CPU 使用率</span><strong>{display_number(resource_value(host_metrics, 'cpu_percent'), ' %')}</strong><small>{host_source_label} · {display_number(resource_value(host_metrics, 'cpu_count'), ' 核')}</small></article>
                <article className="svc-detail-metric"><span>内存使用率</span><strong>{display_number(resource_value(host_metrics, 'memory_percent'), ' %')}</strong><small>{display_bytes(resource_value(host_metrics, 'memory_used_bytes'))} / {display_bytes(resource_value(host_metrics, 'memory_total_bytes'))}</small></article>
                <article className="svc-detail-metric"><span>磁盘使用率</span><strong>{display_number(resource_value(host_metrics, 'disk_used_percent'), ' %')}</strong><small>跨分区最大使用率</small></article>
                <article className="svc-detail-metric"><span>网络连接</span><strong>{display_number(resource_value(host_metrics, 'network_connections'), ' 个')}</strong><small>ESTABLISHED {display_number(resource_value(host_metrics, 'network_established'))} · TIME_WAIT {display_number(resource_value(host_metrics, 'network_time_wait'))}</small></article>
                <article className="svc-detail-metric"><span>Load 1m</span><strong>{display_number(resource_value(host_metrics, 'load_avg_1m'))}</strong><small>主机负载</small></article>
              </div>
              {processes.length > 0 && (
                <div className="svc-detail-attention"><span className="attention-dot attention" /><div><strong>异常进程（{processes.length} 个）</strong><p>{processes.map((item) => { const proc = read_record(item); return `${resource_string(proc, 'name', '未知')} (PID=${resource_value(proc, 'pid')}) CPU ${display_number(resource_value(proc, 'cpu_percent'), '%')} · 内存 ${display_number(resource_value(proc, 'memory_percent'), '%')}` }).join('；')}</p></div></div>
              )}
              <div className="svc-detail-facts"><div><small>采集来源</small><b>{host_source_label}</b></div><div><small>采集范围</small><b>后端所在主机（单主机）</b></div></div>
            </div>
          )
        })()}
      </section>

      <div className="svc-detail-two-col">
        <section className="svc-detail-card">
          <div className="svc-detail-card-head"><div><h3>运行趋势</h3><p>定时采样 · 每 5 分钟 · 保留最近 24 小时 · 历史记录</p></div></div>
          {monitor_query.isPending && <div className="svc-detail-chart-empty"><strong>正在读取历史采样…</strong></div>}
          {monitor_query.isError && <div className="svc-detail-chart-empty"><strong>暂时无法读取历史采样</strong><p>接口不可用时不展示示例趋势。</p></div>}
          {monitor_query.isSuccess && (() => {
            const history = monitor_query.data.data
            const samples = Array.isArray(history.samples) ? history.samples : []
            // P8：异常标记按阈值配置复算（§2.3 唯一文字契约），未配置时使用内置默认（与后端一致）。
            const threshold_config = thresholds_query.data?.data.config
            const anomaly_indices = threshold_config
              ? samples.map((_item, index) => index).filter((index) => is_anomalous_sample(samples, index, threshold_config))
              : []
            if (samples.length === 0) return <div className="svc-detail-chart-empty"><span><Icon name="pulse" size={18} /></span><strong>暂无历史采样</strong><p>{monitor_status_label(history.status)}，不会绘制假趋势线。</p></div>
             return <><div className="svc-detail-chart"><div className="svc-detail-chart-legend"><span>{is_redis ? '内存占用' : 'p95 延迟'}</span><span>{is_redis ? '慢日志' : '慢查询 / 超时'}</span></div><div className="svc-detail-chart-track">{samples.map((item, index) => { const bar = is_redis ? Math.min(100, Math.max(8, (item.memory_bytes ?? 0) / 131072)) : Math.min(100, Math.max(8, (item.p95_ms ?? 0) / 4)); return <div className={`svc-detail-chart-point ${anomaly_indices.includes(index) ? 'anomaly' : ''}`} key={item.id ?? item.observed_at} title={`${display_time(item.observed_at)} · ${is_redis ? display_bytes(item.memory_bytes) : monitor_value(item.p95_ms, ' ms')}`}><i style={{ height: `${bar}%` }} /></div> })}</div><div className="svc-detail-chart-axis"><span>{display_time(samples[0].observed_at)}</span><span>{display_time(samples[samples.length - 1].observed_at)}</span></div>{anomaly_indices.length > 0 && <div className="svc-detail-anomalies"><strong>采样点异常</strong>{anomaly_indices.slice(-5).map((index) => { const item = samples[index]; const reasons = threshold_config ? anomaly_reasons(samples, index, threshold_config) : []; return <span key={item.id ?? item.observed_at}>{display_time(item.observed_at)} · {reasons.join(' / ')}</span> })}</div>}</div>{host_trend_track('主机 CPU', samples, 'host_cpu_percent', 'cpu', ' %')}{host_trend_track('主机内存', samples, 'host_memory_percent', 'mem', ' %')}{host_trend_track('主机磁盘', samples, 'host_disk_used_percent', 'disk', ' %')}</>
          })()}
        </section>
        <section className="svc-detail-card">
          <div className="svc-detail-card-head"><div><h3>当前关注</h3><p>由当前快照和活动摘要形成。</p></div></div>
          <div className="svc-detail-attention"><span className={`attention-dot ${status_class(availability)}`} /><div><strong>{snapshot ? signal_label(resource_value(snapshot, 'performance_signal')) : '暂无可确认的运行信号'}</strong><p>{snapshot ? `数据库信号：${signal_label(resource_value(database, 'signal'))}` : '没有返回可用于判断的快照数据。'}</p></div></div>
          <div className="svc-detail-attention"><span className={`attention-dot ${snapshot_source === 'available' ? 'ok' : 'muted'}`} /><div><strong>数据源：{source_label(snapshot_source)}</strong><p>{snapshot ? '指标来源状态由服务端快照提供。' : '请先完成服务连接或监控配置。'}</p></div></div>
        </section>
      </div>

      <ThresholdConfigCard service_id={id} />

      <section className="svc-detail-section">
        <div className="svc-detail-section-head"><div><h2>服务能力</h2><p>只读能力声明，不代表前端可以直接访问外部服务。</p></div></div>
        <div className="svc-detail-capabilities">
          {investigations.length > 0 ? investigations.map((item, index) => {
            const investigation = read_record(item)
            return <article className="svc-detail-capability" key={resource_string(investigation, 'id', String(index))}><div><span className="capability-mark"><Icon name="check" size={12} /></span><strong>{resource_string(investigation, 'title', '未命名调查')}</strong></div><p>{resource_string(investigation, 'description', '暂无调查说明。')}</p><small>已启用调查入口</small></article>
          }) : <article className="svc-detail-capability muted"><div><span className="capability-mark"><Icon name="minus" size={12} /></span><strong>暂无已启用调查</strong></div><p>当前服务没有返回 supported_investigations。</p><small>未启用</small></article>}
          <article className="svc-detail-capability boundary"><div><span className="capability-mark"><Icon name="shield" size={12} /></span><strong>动作边界</strong></div><p>{action_boundary}</p><small>只读展示</small></article>
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

