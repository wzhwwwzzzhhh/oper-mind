import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  API_V1_DEFAULT_PAGE_SIZE,
  api_v1_client,
  type RunStatus,
} from '../../api/v1/client'
import { api_v1_query_keys, list_services_query } from '../../api/v1/queries'
import { read_items, read_page, read_record, resource_optional_string } from '../workbench/resource-readers'
import { UiAlert, UiButton, UiCard, UiSpace, UiTag, UiText, UiTitle } from '../workbench/ui'

const STATUS_FILTERS: ReadonlyArray<{ key: RunStatus | 'all'; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'queued', label: '排队中' },
  { key: 'running', label: '运行中' },
  { key: 'succeeded', label: '成功' },
  { key: 'failed', label: '失败' },
  { key: 'cancelled', label: '已取消' },
]

const STATUS_COLORS: Record<string, 'green' | 'red' | 'blue' | 'cyan' | 'gold' | 'orange'> = {
  queued: 'gold', running: 'cyan', succeeded: 'green', failed: 'red', cancelled: 'orange',
}

const STATUS_TEXT: Record<string, string> = {
  queued: '排队中', running: '运行中', succeeded: '成功', failed: '失败', cancelled: '已取消',
}

interface GlobalRunView {
  id: string
  session_id: string
  session_title: string
  service_id: string | null
  status: RunStatus
  created_at: string
  error_message: string | null
}

function read_error_message(value: unknown): string | null {
  const error = read_record(value)?.error
  if (!error || typeof error !== 'object') return null
  const message = (error as Record<string, unknown>).message
  return typeof message === 'string' ? message : null
}

function read_run_summary(value: unknown): GlobalRunView | null {
  const id = resource_optional_string(value, 'id')
  const session_id = resource_optional_string(value, 'session_id')
  const session_title = resource_optional_string(value, 'session_title')
  const status = resource_optional_string(value, 'status')
  const created_at = resource_optional_string(value, 'created_at')
  if (!id || !session_id || !session_title || !status || !created_at) return null
  return {
    id,
    session_id,
    session_title,
    service_id: resource_optional_string(value, 'service_id') ?? null,
    status: status as RunStatus,
    created_at,
    error_message: read_error_message(value),
  }
}

function RunRow({ run, on_open }: { run: GlobalRunView; on_open: () => void }): ReactElement {
  return (
    <button className="proposal-row" onClick={on_open} type="button">
      <UiSpace direction="vertical" size={2} style={{ width: '100%', textAlign: 'left' }}>
        <UiSpace wrap>
          <UiTag color={STATUS_COLORS[run.status] ?? 'gold'}>{STATUS_TEXT[run.status] ?? run.status}</UiTag>
          <UiText className="muted-note">{run.created_at}</UiText>
          <UiText className="muted-note">{run.service_id ?? '未关联服务'}</UiText>
        </UiSpace>
        <UiText strong>{run.session_title}</UiText>
        {run.status === 'failed' && run.error_message && (
          <UiText className="muted-note">{run.error_message}</UiText>
        )}
      </UiSpace>
    </button>
  )
}

/** P8 最近调查页：跨会话跨服务 Run 安全摘要，状态/服务过滤 + cursor 分页。 */
export function RunsPage(): ReactElement {
  const navigate = useNavigate()
  const [status, set_status] = useState<RunStatus | 'all'>('all')
  const [service_id, set_service_id] = useState<string>('all')
  const filter_status: RunStatus | undefined = status === 'all' ? undefined : status
  const filter_service: string | undefined = service_id === 'all' ? undefined : service_id

  const services_query = useQuery({ ...list_services_query() })
  const services = useMemo(
    () => services_query.data ? read_items(services_query.data.data) : [],
    [services_query.data],
  )

  const query = useInfiniteQuery({
    queryKey: api_v1_query_keys.runs({ limit: API_V1_DEFAULT_PAGE_SIZE, status: filter_status, service_id: filter_service }),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      api_v1_client.list_runs(
        { cursor: pageParam, limit: API_V1_DEFAULT_PAGE_SIZE, status: filter_status, service_id: filter_service },
        { signal },
      ),
    getNextPageParam: (last_page) => {
      const page = read_page(last_page.data)
      return page.has_more ? page.next_cursor : undefined
    },
  })
  const runs = useMemo(
    () => query.data?.pages.flatMap((page) => read_items(page.data).map(read_run_summary).filter((item): item is GlobalRunView => item !== null)) ?? [],
    [query.data],
  )
  const page_info = query.data?.pages.at(-1) ? read_page(query.data.pages.at(-1)!.data) : undefined

  return (
    <section className="approvals-page" aria-labelledby="runs-title">
      <UiTitle id="runs-title" level={2}>最近调查</UiTitle>
      <UiSpace wrap className="proposal-filters">
        {STATUS_FILTERS.map((item) => (
          <UiButton key={item.key} onClick={() => set_status(item.key)} type={status === item.key ? 'primary' : 'default'}>
            {item.label}
          </UiButton>
        ))}
        <select
          aria-label="按服务过滤调查"
          className="run-service-filter"
          onChange={(event) => set_service_id(event.target.value)}
          value={service_id}
        >
          <option value="all">全部服务</option>
          {services.map((service) => {
            const id = resource_optional_string(service, 'id')
            const title = resource_optional_string(service, 'title')
            if (!id || !title) return null
            return <option key={id} value={id}>{title}</option>
          })}
        </select>
      </UiSpace>
      {query.isPending && <UiText className="muted-note">正在读取调查…</UiText>}
      {query.isError && <UiAlert description="调查列表暂不可读；页面不会用本地数据替代服务端事实。" showIcon title="读取失败" type="error" />}
      {query.isSuccess && runs.length === 0 && (
        <UiText className="muted-note">当前筛选下还没有调查</UiText>
      )}
      {runs.map((run) => (
        <UiCard key={run.id}>
          <RunRow
            on_open={() => navigate(`/workbench/sessions/${encodeURIComponent(run.session_id)}/runs/${encodeURIComponent(run.id)}`)}
            run={run}
          />
        </UiCard>
      ))}
      {page_info?.has_more && (
        <UiButton className="load-more-button" disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()} type="link">
          {query.isFetchingNextPage ? '正在加载…' : '加载更多调查'}
        </UiButton>
      )}
    </section>
  )
}
