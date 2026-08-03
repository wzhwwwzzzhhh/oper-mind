import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { useNavigate } from 'react-router-dom'

import { api_v1_client } from '../../api/v1/client'
import { list_services_query } from '../../api/v1/queries'
import {
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
  if (availability === 'not_configured') return '未接入'
  return String(availability ?? '—')
}

/** 服务中心首页 —— 按设计稿（service-center.html）的服务目录表格。 */
export function ServiceCenterPage(): ReactElement {
  const navigate = useNavigate()
  const query_client = useQueryClient()
  const services_query = useQuery({ ...list_services_query() })
  const services = services_query.data ? read_items(services_query.data.data) : []

  const create_investigation = useMutation({
    mutationFn: (service_id: string) => api_v1_client.create_service_session(service_id, {}),
    onSuccess: async (response) => {
      const session = read_record(response.data.session)
      const session_id = resource_optional_string(session, 'id')
      await query_client.invalidateQueries({ queryKey: ['api-v1', 'sessions'] })
      if (session_id) navigate(`/workbench/sessions/${encodeURIComponent(session_id)}?intent=orders_slow_query.v1`)
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
          <p>管理当前工作空间已授权接入的服务，从服务事实出发进入详情或发起一轮只读调查。</p>
        </div>
        <div className="head-actions">
          <button className="btn" onClick={() => void services_query.refetch()} type="button">↻ 刷新状态</button>
        </div>
      </section>

      <div className="context-strip">
        <div className="context-stat">
          <small>当前工作空间</small>
          <strong>研发运维团队</strong>
          <span>platform-team · 受控访问</span>
        </div>
        <div className="context-stat">
          <small>服务状态</small>
          <strong>{services.length} 个服务</strong>
          <span>{services.length} 个已接入</span>
        </div>
        <div className="context-stat">
          <small>默认权限</small>
          <strong>只读调查</strong>
          <span>变更操作需要人工审批</span>
        </div>
        <div className="context-stat">
          <small>最近同步</small>
          <strong>刚刚</strong>
          <span>状态按需刷新</span>
        </div>
      </div>

      <section className="section">
        <div className="section-head">
          <h2>服务目录</h2>
          <span>仅展示当前工作空间授权范围内的信息</span>
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
              <span>服务</span>
              <span>类型 / 环境</span>
              <span>状态</span>
              <span>能力</span>
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
              return (
                <article className="service-row" key={service_id ?? title}>
                  <div className="service-main">
                    <div className={`service-logo ${logo_class(kind)}`}>{info.short}</div>
                    <div className="service-name">
                      <strong>{title}</strong>
                      <span>{info.label} · 已接入</span>
                    </div>
                  </div>
                  <div className="type">
                    {info.label}
                    <small>受控访问</small>
                  </div>
                  <div>
                    <span className={`state ${state}`}>{availability_text(availability)}</span>
                  </div>
                  <div className="fact">
                    <strong>只读</strong>
                    <span>受控调查</span>
                  </div>
                  <div className="actions">
                    {service_id && (
                      <>
                        <button onClick={() => navigate(`/services/${encodeURIComponent(service_id)}`)} type="button">查看详情</button>
                        <button
                          className="investigate"
                          disabled={create_investigation.isPending}
                          onClick={() => create_investigation.mutate(service_id)}
                          type="button"
                        >
                          发起调查
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
