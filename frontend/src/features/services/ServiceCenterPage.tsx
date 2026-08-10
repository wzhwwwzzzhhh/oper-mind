import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import type { ReactElement } from 'react'
import { useNavigate } from 'react-router-dom'

import { api_v1_client } from '../../api/v1/client'
import { list_services_query } from '../../api/v1/queries'
import { Icon } from '../shell/Icon'
import {
  read_array,
  read_items,
  read_record,
  resource_optional_string,
  resource_string,
  resource_value,
} from '../workbench/resource-readers'

function service_kind_label(kind: unknown): { short: string; label: string } {
  const text = String(kind ?? '').toLowerCase()
  if (text.includes('postgres')) return { short: 'PG', label: 'PostgreSQL' }
  if (text.includes('mysql')) return { short: 'my', label: 'MySQL' }
  if (text.includes('redis')) return { short: 'Re', label: 'Redis' }
  if (text.includes('kubernetes') || text.includes('k8s')) return { short: 'K8s', label: 'Kubernetes' }
  return { short: 'Sv', label: text || '服务' }
}

function logo_class(kind: unknown): string {
  const text = String(kind ?? '').toLowerCase()
  if (text.includes('postgres')) return 'pg'
  if (text.includes('mysql')) return 'mysql'
  if (text.includes('redis')) return 'redis'
  if (text.includes('kubernetes') || text.includes('k8s')) return 'k8s'
  return ''
}

function availability_state(availability: unknown): 'ok' | 'attention' | 'muted' {
  if (availability === 'healthy') return 'ok'
  if (availability === 'unhealthy') return 'attention'
  return 'muted'
}

function availability_text(availability: unknown): string {
  if (availability === 'healthy') return '正常'
  if (availability === 'unhealthy') return '需关注'
  if (availability === 'not_configured') return '未配置'
  return String(availability ?? '—')
}

/** 快照模式 → 中文说明；对应后端 ServiceMode。 */
function mode_text(mode: unknown): string {
  if (mode === 'mock') return '演示快照'
  if (mode === 'target') return '目标快照'
  if (mode === 'disabled') return '未接入'
  return '—'
}

/** 最近一次成功读取时刻；用 react-query 的 dataUpdatedAt，不写死"刚刚"。 */
function sync_text(updated_at: number): string {
  if (updated_at === 0) return '尚未读取'
  return new Date(updated_at).toLocaleTimeString('zh-CN', { hour: '2-digit', hour12: false, minute: '2-digit', second: '2-digit' })
}

/** 服务中心首页 —— 按设计稿（service-center.html）的服务目录表格。 */
export function ServiceCenterPage(): ReactElement {
  const navigate = useNavigate()
  const query_client = useQueryClient()
  const pending_intent = useRef<string | null>(null)
  const [selected_service_ids, set_selected_service_ids] = useState<string[]>([])
  const services_query = useQuery({ ...list_services_query() })
  const services = services_query.data ? read_items(services_query.data.data) : []
  const configured_count = services.filter(
    (service) => resource_optional_string(resource_value(service, 'snapshot'), 'availability') !== 'not_configured',
  ).length

  const create_investigation = useMutation({
    mutationFn: ({ service_id, intent }: { service_id: string; intent: string | null }) => {
      pending_intent.current = intent
      return api_v1_client.create_service_session(service_id, {})
    },
    onSuccess: async (response) => {
      const session = read_record(response.data.session)
      const session_id = resource_optional_string(session, 'id')
      await query_client.invalidateQueries({ queryKey: ['api-v1', 'sessions'] })
      const intent = pending_intent.current
      pending_intent.current = null
      if (session_id) {
        navigate(`/workbench/sessions/${encodeURIComponent(session_id)}${intent ? `?intent=${encodeURIComponent(intent)}` : ''}`)
      }
    },
  })
  const create_batch_investigation = useMutation({
    mutationFn: (service_ids: string[]) => api_v1_client.create_session({
      service_ids,
      title: '联合服务调查',
    }),
    onSuccess: async (response) => {
      const session_id = resource_optional_string(read_record(response.data.session), 'id')
      await query_client.invalidateQueries({ queryKey: ['api-v1', 'sessions'] })
      if (session_id) navigate(`/workbench/sessions/${encodeURIComponent(session_id)}`)
    },
  })

  return (
    <div className="svc-page">
      <div className="breadcrumb">
        <span>会话工作台</span>
        <span>/</span>
        <strong>服务中心</strong>
      </div>

      <section className="page-head">
        <div>
          <div className="eyebrow">Service workspace</div>
          <h1>服务中心</h1>
          <p>查看后端已注册接入的服务，从服务事实出发进入详情或发起一轮只读调查。</p>
        </div>
        <div className="head-actions">
          <button className="btn" disabled={services_query.isFetching} onClick={() => void services_query.refetch()} type="button">
            <Icon name="refresh" size={13} />
            {services_query.isFetching ? '读取中…' : '刷新状态'}
          </button>
        </div>
      </section>

      <div className="svc-context-strip">
        <div className="context-stat">
          <small>已注册服务</small>
          <strong>{services_query.isSuccess ? `${services.length} 个服务` : '—'}</strong>
          <span>
            {services_query.isSuccess
              ? `${configured_count} 个已配置快照`
              : '尚未读取到服务列表'}
          </span>
        </div>
        <div className="context-stat">
          <small>默认权限</small>
          <strong>只读调查</strong>
          <span>变更动作需人工审批</span>
        </div>
        <div className="context-stat">
          <small>最近读取</small>
          <strong>{sync_text(services_query.dataUpdatedAt)}</strong>
          <span>按需刷新，不做后台轮询</span>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>服务目录</h2>
          <div className="service-batch-actions">
            <span>仅展示后端已注册服务，按需读取，不做后台轮询</span>
            <button
              className="btn"
              disabled={selected_service_ids.length === 0 || create_batch_investigation.isPending}
              onClick={() => create_batch_investigation.mutate(selected_service_ids)}
              type="button"
            >
              联合发起调查 ({selected_service_ids.length})
            </button>
          </div>
        </div>

        {services_query.isPending && <div className="svc-empty">正在读取服务中心…</div>}
        {services_query.isError && <div className="svc-empty">暂时无法读取服务中心。</div>}

        {services_query.isSuccess && services.length === 0 && (
          <div className="svc-empty">
            当前还没有已接入的服务。服务接入能力（PostgreSQL / MySQL / Redis 等）将在后续工作包提供；
            页面不会用示例数据伪装真实服务。
          </div>
        )}

        {services.length > 0 && (
          <div className="catalog">
            <div className="catalog-head">
              <span>选择</span>
              <span>服务</span>
              <span>类型 / 快照模式</span>
              <span>状态</span>
              <span>已启用调查</span>
              <span>操作</span>
            </div>
            {services.map((service) => {
              const service_id = resource_optional_string(service, 'id')
              const title = resource_string(service, 'title', '未命名服务')
              const kind = resource_optional_string(service, 'kind')
              const info = service_kind_label(kind)
              const snapshot = resource_value(service, 'snapshot')
              const availability = resource_optional_string(snapshot, 'availability')
              const state = availability_state(availability)
              const investigations = read_array(resource_value(service, 'supported_investigations'))
              const first_investigation = read_record(investigations[0])
              const intent = resource_optional_string(first_investigation, 'id') ?? null
              return (
                <article className="service-row" key={service_id ?? title}>
                  <div>
                    {service_id && (
                      <input
                        aria-label={`选择 ${title}`}
                        checked={selected_service_ids.includes(service_id)}
                        onChange={(event) => set_selected_service_ids((current) => event.target.checked
                          ? [...current, service_id]
                          : current.filter((id) => id !== service_id))}
                        type="checkbox"
                      />
                    )}
                  </div>
                  <div className="service-main">
                    <div className={`service-logo ${logo_class(kind)}`}>{info.short}</div>
                    <div className="service-name">
                      <strong>{title}</strong>
                      <span>{info.label} · {availability === 'not_configured' ? '未配置' : '已接入'}</span>
                    </div>
                  </div>
                  <div className="type">
                    {info.label}
                    <small>{mode_text(resource_optional_string(snapshot, 'mode'))}</small>
                  </div>
                  <div>
                    <span className={`state ${state}`}>{availability_text(availability)}</span>
                  </div>
                  <div className="fact">
                    <strong>{investigations.length > 0 ? `${investigations.length} 项` : '无'}</strong>
                    <span>{investigations.length > 0 ? '只读调查' : '未启用调查入口'}</span>
                  </div>
                  <div className="actions">
                    {service_id && (
                      <>
                        <button onClick={() => navigate(`/services/${encodeURIComponent(service_id)}`)} type="button">查看详情</button>
                        <button
                          className="investigate"
                          disabled={create_investigation.isPending || intent === null}
                          onClick={() => create_investigation.mutate({ service_id, intent })}
                          title={intent === null ? '调查能力未启用' : undefined}
                          type="button"
                        >
                          {intent === null ? '未启用' : '发起调查'}
                        </button>
                      </>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
