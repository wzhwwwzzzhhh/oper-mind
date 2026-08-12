import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  API_V1_DEFAULT_PAGE_SIZE,
  api_v1_client,
  type AuditActivityType,
  type AuditOutcome,
} from '../../api/v1/client'
import { api_v1_query_keys, list_services_query } from '../../api/v1/queries'
import { read_items, read_page, resource_optional_string } from '../workbench/resource-readers'
import { UiButton, UiTag } from '../workbench/ui'

const TYPE_OPTIONS: ReadonlyArray<{ key: AuditActivityType | 'all'; label: string }> = [
  { key: 'all', label: '全部类型' },
  { key: 'run_created', label: '调查已受理' },
  { key: 'run_running', label: '调查进行中' },
  { key: 'run_completed', label: '调查完成' },
  { key: 'run_failed', label: '调查失败' },
  { key: 'run_cancelled', label: '调查已取消' },
  { key: 'proposal_created', label: '提案已生成' },
  { key: 'approval_recorded', label: '审批已记录' },
  { key: 'execution_completed', label: '执行完成' },
  { key: 'verification_completed', label: '验证完成' },
  { key: 'action_blocked', label: '动作被拦截' },
  { key: 'action_failed', label: '动作失败' },
]

const OUTCOME_OPTIONS: ReadonlyArray<{ key: AuditOutcome | 'all'; label: string }> = [
  { key: 'all', label: '全部结果' },
  { key: 'running', label: '进行中' },
  { key: 'succeeded', label: '成功' },
  { key: 'failed', label: '失败' },
  { key: 'cancelled', label: '已取消' },
  { key: 'pending_approval', label: '待审批' },
  { key: 'approved', label: '已批准' },
  { key: 'rejected', label: '已拒绝' },
  { key: 'expired', label: '已过期' },
  { key: 'blocked', label: '已拦截' },
  { key: 'verified', label: '已验证' },
]

const TYPE_TEXT: Record<string, string> = Object.fromEntries(
  TYPE_OPTIONS.filter((item) => item.key !== 'all').map((item) => [item.key as string, item.label]),
)

const OUTCOME_COLORS: Record<string, 'green' | 'red' | 'blue' | 'cyan' | 'gold' | 'orange'> = {
  running: 'cyan', succeeded: 'green', failed: 'red', cancelled: 'orange',
  pending_approval: 'gold', approved: 'blue', rejected: 'red', expired: 'red',
  blocked: 'red', verified: 'green',
}

const OUTCOME_TEXT: Record<string, string> = Object.fromEntries(
  OUTCOME_OPTIONS.filter((item) => item.key !== 'all').map((item) => [item.key as string, item.label]),
)

interface AuditActivityView {
  id: string
  kind: 'run' | 'action'
  type: string
  occurred_at: string
  service_id: string | null
  session_id: string
  session_title: string
  outcome: string
  summary: string | null
  run_id: string | null
  proposal_id: string | null
  approval_actor: string | null
}

function read_activity(value: unknown): AuditActivityView | null {
  const id = resource_optional_string(value, 'id')
  const kind = resource_optional_string(value, 'kind')
  const type = resource_optional_string(value, 'type')
  const occurred_at = resource_optional_string(value, 'occurred_at')
  const session_id = resource_optional_string(value, 'session_id')
  const session_title = resource_optional_string(value, 'session_title')
  const outcome = resource_optional_string(value, 'outcome')
  if (!id || !kind || !type || !occurred_at || !session_id || !session_title || !outcome) return null
  return {
    id,
    kind: kind as 'run' | 'action',
    type,
    occurred_at,
    service_id: resource_optional_string(value, 'service_id') ?? null,
    session_id,
    session_title,
    outcome,
    summary: resource_optional_string(value, 'summary') ?? null,
    run_id: resource_optional_string(value, 'run_id') ?? null,
    proposal_id: resource_optional_string(value, 'proposal_id') ?? null,
    approval_actor: resource_optional_string(value, 'approval_actor') ?? null,
  }
}

function display_time(value: string): string {
  return value.replace('T', ' ').replace('Z', '').slice(0, 16)
}

function ActivityRow({
  item,
  service_title,
  on_open,
}: {
  item: AuditActivityView
  service_title: string
  on_open: () => void
}): ReactElement {
  const anchor = item.kind === 'run' ? item.run_id : item.proposal_id
  const content = (
    <>
      <div className="audit-type">
        <UiTag color={item.kind === 'action' ? 'blue' : 'cyan'}>{TYPE_TEXT[item.type] ?? item.type}</UiTag>
        <small>{item.kind === 'action' ? '受控动作' : '调查 Run'}</small>
      </div>
      <div className="audit-outcome">
        <UiTag color={OUTCOME_COLORS[item.outcome] ?? 'gold'}>{OUTCOME_TEXT[item.outcome] ?? item.outcome}</UiTag>
        {item.approval_actor !== null && <small>审批人：{item.approval_actor}</small>}
      </div>
      <div className="audit-service">
        <strong>{service_title}</strong>
        <small>{item.service_id ?? '未绑定服务'}</small>
      </div>
      <div className="audit-session">
        <strong>{item.session_title}</strong>
        <small>{display_time(item.occurred_at)}</small>
      </div>
      <div className="audit-summary">
        <span>{item.summary ?? '暂无摘要'}</span>
      </div>
      <span className="audit-detail-cue">
        {anchor !== null ? '查看详情' : ''}
      </span>
    </>
  )
  if (anchor === null) {
    return <div className="audit-row">{content}</div>
  }
  return (
    <button className="audit-row audit-row-button" onClick={on_open} type="button">
      {content}
    </button>
  )
}

/** P8 审计操作记录页：跨服务跨会话的活动留痕，支持时间窗/服务/类型/结果过滤。 */
export function AuditPage(): ReactElement {
  const navigate = useNavigate()
  const [service_id, set_service_id] = useState<string>('all')
  const [action_type, set_action_type] = useState<AuditActivityType | 'all'>('all')
  const [result, set_result] = useState<AuditOutcome | 'all'>('all')
  const [from_value, set_from_value] = useState('')
  const [to_value, set_to_value] = useState('')
  const [applied_from, set_applied_from] = useState<string | undefined>()
  const [applied_to, set_applied_to] = useState<string | undefined>()

  const services_query = useQuery({ ...list_services_query() })
  const service_titles: Record<string, string> = {}
  for (const item of read_items(services_query.data?.data)) {
    const id = resource_optional_string(item, 'id')
    const title = resource_optional_string(item, 'title')
    if (id && title) service_titles[id] = title
  }

  const filter_service = service_id === 'all' ? undefined : service_id
  const filter_type = action_type === 'all' ? undefined : action_type
  const filter_result = result === 'all' ? undefined : result

  const query = useInfiniteQuery({
    queryKey: api_v1_query_keys.audit_activities({
      limit: API_V1_DEFAULT_PAGE_SIZE,
      service_id: filter_service,
      action_type: filter_type,
      result: filter_result,
      from: applied_from,
      to: applied_to,
    }),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      api_v1_client.list_audit_activities(
        {
          cursor: pageParam,
          limit: API_V1_DEFAULT_PAGE_SIZE,
          service_id: filter_service,
          action_type: filter_type,
          result: filter_result,
          from: applied_from,
          to: applied_to,
        },
        { signal },
      ),
    getNextPageParam: (last_page) => {
      const page = read_page(last_page.data)
      return page.has_more ? page.next_cursor : undefined
    },
  })
  const activities = query.data?.pages.flatMap((page) => read_items(page.data).map(read_activity).filter((item): item is AuditActivityView => item !== null)) ?? []
  const page_info = query.data?.pages.at(-1) ? read_page(query.data.pages.at(-1)!.data) : undefined

  const apply_window = (): void => {
    set_applied_from(from_value ? new Date(from_value).toISOString() : undefined)
    set_applied_to(to_value ? new Date(to_value).toISOString() : undefined)
  }
  const reset_filters = (): void => {
    set_service_id('all')
    set_action_type('all')
    set_result('all')
    set_from_value('')
    set_to_value('')
    set_applied_from(undefined)
    set_applied_to(undefined)
  }

  const open_activity = (item: AuditActivityView): void => {
    if (item.kind === 'run' && item.run_id) {
      navigate(`/workbench/sessions/${encodeURIComponent(item.session_id)}/runs/${encodeURIComponent(item.run_id)}`)
    } else if (item.kind === 'action' && item.proposal_id) {
      navigate(`/workbench/approvals/${encodeURIComponent(item.proposal_id)}`)
    }
  }

  return (
    <div className="svc-page">
      <div className="breadcrumb">
        <span>服务中心</span>
        <span>/</span>
        <strong>审计操作记录</strong>
      </div>

      <section className="page-head">
        <div>
          <div className="eyebrow">Audit trail</div>
          <h1>审计操作记录</h1>
          <p>跨服务跨会话的活动留痕：调查 Run 与受控动作（提案 / 审批 / 执行 / 验证）的安全摘要。</p>
        </div>
        <div className="head-actions">
          <button className="btn" disabled={query.isFetching} onClick={() => void query.refetch()} type="button">
            {query.isFetching ? '读取中…' : '刷新'}
          </button>
        </div>
      </section>

      <div className="monitor-honesty-strip">
        数据来源：系统活动留痕 · 只读 · 不含原始证据、工具输出与凭据
      </div>

      <section className="section">
        <div className="section-head">
          <h2>活动记录</h2>
          <div className="audit-filters">
            <select
              aria-label="服务过滤"
              onChange={(event) => set_service_id(event.target.value)}
              value={service_id}
            >
              <option value="all">全部服务</option>
              {Object.entries(service_titles).map(([id, title]) => (
                <option key={id} value={id}>{title}</option>
              ))}
            </select>
            <select
              aria-label="类型过滤"
              onChange={(event) => set_action_type(event.target.value as AuditActivityType | 'all')}
              value={action_type}
            >
              {TYPE_OPTIONS.map((item) => (
                <option key={item.key} value={item.key}>{item.label}</option>
              ))}
            </select>
            <select
              aria-label="结果过滤"
              onChange={(event) => set_result(event.target.value as AuditOutcome | 'all')}
              value={result}
            >
              {OUTCOME_OPTIONS.map((item) => (
                <option key={item.key} value={item.key}>{item.label}</option>
              ))}
            </select>
            <label className="audit-window">
              <span>从</span>
              <input
                aria-label="时间窗起点"
                onChange={(event) => set_from_value(event.target.value)}
                onBlur={apply_window}
                type="datetime-local"
                value={from_value}
              />
            </label>
            <label className="audit-window">
              <span>至</span>
              <input
                aria-label="时间窗终点"
                onChange={(event) => set_to_value(event.target.value)}
                onBlur={apply_window}
                type="datetime-local"
                value={to_value}
              />
            </label>
            <UiButton onClick={reset_filters} type="default">重置过滤</UiButton>
          </div>
        </div>

        {query.isPending && <div className="svc-empty">正在读取审计活动…</div>}
        {query.isError && (
          <div className="svc-empty">
            <strong>暂时无法读取审计活动</strong>
            <p>接口不可用时不展示示例数据，请稍后重试。</p>
            <button className="btn" onClick={() => void query.refetch()} type="button">重试</button>
          </div>
        )}
        {query.isSuccess && activities.length === 0 && (
          <div className="svc-empty">当前过滤条件下没有活动记录。</div>
        )}

        {activities.length > 0 && (
          <div className="audit-table">
            <div className="audit-table-head">
              <span>类型</span>
              <span>结果</span>
              <span>服务</span>
              <span>会话 / 时间</span>
              <span>脱敏摘要</span>
              <span />
            </div>
            {activities.map((item) => (
              <ActivityRow
                item={item}
                key={item.id}
                on_open={() => open_activity(item)}
                service_title={item.service_id ? (service_titles[item.service_id] ?? item.service_id) : '—'}
              />
            ))}
          </div>
        )}
        {page_info?.has_more && (
          <UiButton
            className="load-more-button"
            disabled={query.isFetchingNextPage}
            onClick={() => void query.fetchNextPage()}
            type="link"
          >
            {query.isFetchingNextPage ? '正在加载…' : '加载更多活动'}
          </UiButton>
        )}
      </section>
    </div>
  )
}
