import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import type { FormEvent, ReactElement } from 'react'
import { useNavigate } from 'react-router-dom'

import { api_v1_client } from '../../api/v1/client'
import {
  create_service_mutation,
  delete_service_mutation,
  list_services_query,
  test_service_connection_mutation,
  update_service_mutation,
} from '../../api/v1/queries'
import { Icon } from '../shell/Icon'
import {
  read_array,
  read_items,
  read_record,
  resource_optional_string,
  resource_string,
  resource_value,
} from '../workbench/resource-readers'

interface ServiceFormState {
  kind: string
  instance_id: string
  title: string
  dsn: string
}

const empty_form: ServiceFormState = { kind: 'postgres', instance_id: '', title: '', dsn: '' }

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
  const [toast, set_toast] = useState<string | null>(null)
  const [form_open, set_form_open] = useState(false)
  const [editing, set_editing] = useState<{ id: string; title: string; kind: string } | null>(null)
  const [form, set_form] = useState<ServiceFormState>(empty_form)
  const [deleting, set_deleting] = useState<{ id: string; title: string } | null>(null)
  const services_query = useQuery({ ...list_services_query() })
  const services = services_query.data ? read_items(services_query.data.data) : []
  const configured_count = services.filter(
    (service) => resource_optional_string(resource_value(service, 'snapshot'), 'availability') !== 'not_configured',
  ).length

  const show_toast = (message: string): void => {
    set_toast(message)
    window.setTimeout(() => set_toast(null), 1800)
  }

  const refresh = (): void => {
    void query_client.invalidateQueries({ queryKey: ['api-v1', 'services'] })
  }

  const create_mutation = useMutation({
    ...create_service_mutation(),
    onSuccess: () => {
      set_form_open(false)
      set_form(empty_form)
      refresh()
      show_toast('服务已接入。')
    },
    onError: (error) => show_toast(error instanceof Error ? error.message : '接入服务失败。'),
  })

  const update_mutation = useMutation({
    ...update_service_mutation(),
    onSuccess: () => {
      set_form_open(false)
      set_editing(null)
      set_form(empty_form)
      refresh()
      show_toast('服务已更新。')
    },
    onError: (error) => show_toast(error instanceof Error ? error.message : '更新服务失败。'),
  })

  const delete_mutation = useMutation({
    ...delete_service_mutation(),
    onSuccess: () => {
      set_deleting(null)
      refresh()
      show_toast('服务已移除。')
    },
    onError: (error) => show_toast(error instanceof Error ? error.message : '移除服务失败。'),
  })

  const test_connection_mutation = useMutation({
    ...test_service_connection_mutation(),
    onSuccess: (response) => {
      const availability = resource_optional_string(read_record(response.data), 'availability')
      const label = availability === 'healthy' ? '连接正常' : availability === 'not_configured' ? '未配置' : '不可达'
      refresh()
      show_toast(`连接测试：${label}。`)
    },
    onError: (error) => show_toast(error instanceof Error ? error.message : '连接测试失败。'),
  })

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

  const open_create = (): void => {
    set_editing(null)
    set_form(empty_form)
    set_form_open(true)
  }

  const open_edit = (service: { id: string; title: string; kind: string }): void => {
    set_editing(service)
    set_form({ kind: service.kind, instance_id: service.id, title: service.title, dsn: '' })
    set_form_open(true)
  }

  const set_form_field = (field: keyof ServiceFormState, value: string): void => {
    set_form((current) => ({ ...current, [field]: value }))
  }

  const submit_form = (event: FormEvent): void => {
    event.preventDefault()
    const kind = form.kind.trim()
    const instance_id = form.instance_id.trim()
    const title = form.title.trim()
    const dsn = form.dsn.trim()
    if (editing != null) {
      update_mutation.mutate({ service_id: editing.id, title, dsn: dsn === '' ? undefined : dsn })
    } else {
      create_mutation.mutate({ kind, instance_id, title, dsn })
    }
  }

  const saving = create_mutation.isPending || update_mutation.isPending

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
          <button className="btn primary" onClick={open_create} type="button">
            ＋ 添加服务
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
            当前还没有已接入的服务。点击「＋ 添加服务」接入 PostgreSQL / Redis / MySQL 实例；
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
              const has_dsn = resource_value(service, 'has_dsn')
              const masked_tail = resource_optional_string(service, 'dsn_masked_tail')
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
                    {has_dsn === true && masked_tail != null && <small>DSN 已存 · 尾号 {masked_tail}</small>}
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
                          disabled={test_connection_mutation.isPending}
                          onClick={() => test_connection_mutation.mutate(service_id)}
                          type="button"
                        >
                          测试连接
                        </button>
                        <button
                          onClick={() => open_edit({ id: service_id, title, kind: kind ?? '' })}
                          type="button"
                        >
                          编辑
                        </button>
                        <button
                          onClick={() => set_deleting({ id: service_id, title })}
                          type="button"
                        >
                          移除
                        </button>
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

      {form_open && <div className="model-modal" role="dialog" aria-modal="true" aria-labelledby="svc-modal-title"><div className="model-dialog">
        <div className="model-dialog-head">
          <div>
            <strong id="svc-modal-title">{editing != null ? `编辑 ${editing.title}` : '接入服务'}</strong>
            <p>{editing != null ? '修改标题或 DSN。DSN 留空保持不变；能力声明由服务类型决定。' : '填写服务类型、实例 ID、标题与 DSN。DSN 加密保存、绝不回显明文。'}</p>
          </div>
          <button aria-label="关闭" className="icon-btn" onClick={() => { set_form_open(false); set_editing(null); }} type="button"><Icon name="x" size={14} /></button>
        </div>
        <form className="provider-form" onSubmit={submit_form}>
          <label>服务类型
            <select aria-label="服务类型" value={form.kind} onChange={(event) => set_form_field('kind', event.target.value)} disabled={editing != null}>
              <option value="postgres">PostgreSQL</option>
              <option value="redis">Redis</option>
              <option value="mysql">MySQL</option>
            </select>
          </label>
          <label>实例 ID<input aria-label="实例 ID" required value={form.instance_id} onChange={(event) => set_form_field('instance_id', event.target.value)} type="text" placeholder="如 postgres-orders" disabled={editing != null} /></label>
          <label>标题<input aria-label="标题" required value={form.title} onChange={(event) => set_form_field('title', event.target.value)} type="text" placeholder="订单 PostgreSQL" /></label>
          <label>DSN<input aria-label="DSN" required={editing == null} value={form.dsn} onChange={(event) => set_form_field('dsn', event.target.value)} type="text" autoComplete="off" placeholder={editing != null ? '留空保持不变' : 'postgresql://user:pass@host:5432/db'} /></label>
          <div className="model-dialog-footer"><button className="model-button" type="button" onClick={() => { set_form_open(false); set_editing(null); }}>取消</button><button className="model-button primary" type="submit" disabled={saving}>{editing != null ? '保存修改' : '接入服务'}</button></div>
        </form>
      </div></div>}

      {deleting != null && <div className="model-modal" role="dialog" aria-modal="true" aria-labelledby="svc-delete-title"><div className="model-dialog">
        <div className="model-dialog-head"><div><strong id="svc-delete-title">移除服务</strong><p>将移除「{deleting.title}」及其加密凭据。已有关联的会话 / 监控 / 活动留痕不会删除。</p></div><button aria-label="关闭" className="icon-btn" onClick={() => set_deleting(null)} type="button"><Icon name="x" size={14} /></button></div>
        <div className="model-dialog-footer"><button className="model-button" type="button" onClick={() => set_deleting(null)}>取消</button><button className="model-button primary" type="button" onClick={() => delete_mutation.mutate(deleting.id)} disabled={delete_mutation.isPending}>确认移除</button></div>
      </div></div>}

      {toast && <div className="model-toast" role="status">{toast}</div>}
    </div>
  )
}
