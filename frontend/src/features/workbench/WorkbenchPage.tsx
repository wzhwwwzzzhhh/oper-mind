import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Empty,
  Input,
  Skeleton,
  Space,
  Tag,
  Timeline,
  Typography,
} from 'antd'
import type { ReactElement, ReactNode } from 'react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import {
  API_V1_DEFAULT_PAGE_SIZE,
  ApiClientError,
  api_v1_client,
  type ApiResponse,
  type RunResponse,
  type SessionResponse,
} from '../../api/v1/client'
import {
  api_v1_query_keys,
  create_run_mutation,
  get_run_query,
  get_session_query,
} from '../../api/v1/queries'
import {
  read_items,
  read_page,
  resource_optional_string,
  resource_string,
  resource_value,
} from './resource-readers'
import { merge_persisted_run_events, run_event_summary, type PersistedRunEvent } from './run-events'
import { use_run_event_stream } from './use-run-event-stream'

function safe_error(error: unknown): { title: string; detail: ReactNode } {
  if (error instanceof ApiClientError) {
    const request_id = error.diagnostics.meta_request_id ?? error.diagnostics.response_request_id
    const trace_id = error.diagnostics.meta_trace_id ?? error.diagnostics.response_trace_id
    return {
      title: `${error.code}：${error.message}`,
      detail: (
        <Space size="small" wrap>
          {request_id && <Tag>请求 {request_id}</Tag>}
          {trace_id && <Tag color="cyan">Trace {trace_id}</Tag>}
        </Space>
      ),
    }
  }

  return { title: '暂时无法读取服务数据。', detail: '请稍后刷新；工作台不会使用本地数据代替服务端事实。' }
}

function status_color(status: string): string {
  if (status === 'succeeded' || status === 'active') return 'green'
  if (status === 'failed') return 'red'
  if (status === 'running') return 'blue'
  if (status === 'queued') return 'gold'
  return 'default'
}

function LoadingBlock({ label }: { label: string }): ReactElement {
  return (
    <div aria-label={label} className="workbench-loading">
      <Skeleton active paragraph={{ rows: 4 }} title />
    </div>
  )
}

function ApiErrorNotice({ error }: { error: unknown }): ReactElement {
  const safe = safe_error(error)
  return <Alert description={safe.detail} title={safe.title} showIcon type="error" />
}

interface RetryableRunRequest {
  idempotency_key: string
  query: string
}

function is_retryable_unknown_error(error: unknown): boolean {
  return error instanceof ApiClientError && (
    error.code === 'NETWORK_ERROR' || error.code === 'INVALID_API_RESPONSE'
  )
}

function RunSubmissionPanel({
  session_id,
  session_status,
}: {
  session_id: string
  session_status: string
}): ReactElement {
  const navigate = useNavigate()
  const query_client = useQueryClient()
  const create_run = useMutation(create_run_mutation())
  const [query, set_query] = useState('')
  const [retry_request, set_retry_request] = useState<RetryableRunRequest | undefined>()
  const active_session = session_status === 'active'

  function accept_run(response: ApiResponse<RunResponse>): void {
    const accepted_run_id = resource_optional_string(response.data.run, 'id')
    if (!accepted_run_id) return

    void Promise.all([
      query_client.invalidateQueries({ queryKey: ['api-v1', 'session-runs', session_id] }),
      query_client.invalidateQueries({ queryKey: ['api-v1', 'session-messages', session_id] }),
      query_client.invalidateQueries({ queryKey: api_v1_query_keys.run(accepted_run_id) }),
    ])
    navigate(
      `/workbench/sessions/${encodeURIComponent(session_id)}/runs/${encodeURIComponent(accepted_run_id)}`,
    )
  }

  function submit_run(request: RetryableRunRequest): void {
    create_run.mutate(
      { session_id, query: request.query, idempotency_key: request.idempotency_key },
      {
        onError: (error) => {
          if (is_retryable_unknown_error(error)) {
            set_retry_request(request)
          }
        },
        onSuccess: (response) => {
          set_retry_request(undefined)
          accept_run(response)
        },
      },
    )
  }

  function start_new_run(): void {
    const normalized_query = query.trim()
    if (!normalized_query || create_run.isPending || !active_session) return

    set_retry_request(undefined)
    create_run.reset()
    submit_run({ idempotency_key: globalThis.crypto.randomUUID(), query: normalized_query })
  }

  function update_query(next_query: string): void {
    set_query(next_query)
    if (retry_request && next_query !== retry_request.query) {
      set_retry_request(undefined)
    }
    if (create_run.isError) create_run.reset()
  }

  return (
    <Card className="workbench-card" size="small" title="发起诊断">
      {!active_session && (
        <Alert
          description="会话已归档，仅可读取历史内容，不能受理新的诊断运行。"
          title="已归档会话"
          showIcon
          type="info"
        />
      )}
      {active_session && (
        <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            描述需要诊断的问题。提交后服务端以幂等键受理；页面刷新不会自动重新提交。
          </Typography.Text>
          <Input.TextArea
            aria-label="诊断问题"
            autoSize={{ minRows: 3, maxRows: 8 }}
            disabled={create_run.isPending}
            maxLength={4000}
            onChange={(event) => update_query(event.target.value)}
            placeholder="例如：请检查 Nginx 5xx 的根因和影响范围"
            value={query}
          />
          <Space wrap>
            <Button
              disabled={!query.trim() || create_run.isPending}
              loading={create_run.isPending}
              onClick={start_new_run}
              type="primary"
            >
              开始诊断
            </Button>
            {retry_request && !create_run.isPending && (
              <Button onClick={() => submit_run(retry_request)} type="default">
                按原请求重试
              </Button>
            )}
          </Space>
          {create_run.isError && <ApiErrorNotice error={create_run.error} />}
          {retry_request && (
            <Typography.Text type="secondary">
              上次请求的受理结果未知；重试会复用原幂等键和未修改的问题，不会自动创建新的诊断运行。
            </Typography.Text>
          )}
        </Space>
      )}
    </Card>
  )
}

function LoadMoreButton({
  has_more,
  is_fetching,
  on_click,
}: {
  has_more: boolean
  is_fetching: boolean
  on_click: () => void
}): ReactElement | null {
  if (!has_more) return null

  return (
    <Button disabled={is_fetching} onClick={on_click} type="link">
      {is_fetching ? '正在加载…' : '加载更多'}
    </Button>
  )
}

function SessionNavigator(): ReactElement {
  const navigate = useNavigate()
  const sessions_query = useInfiniteQuery({
    queryKey: api_v1_query_keys.sessions({ limit: API_V1_DEFAULT_PAGE_SIZE, status: 'active' }),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      api_v1_client.list_sessions(
        { cursor: pageParam, limit: API_V1_DEFAULT_PAGE_SIZE, status: 'active' },
        { signal },
      ),
    getNextPageParam: (last_page) => {
      const page = read_page(last_page.data)
      return page.has_more ? page.next_cursor : undefined
    },
  })
  const sessions = useMemo(
    () => sessions_query.data?.pages.flatMap((page) => read_items(page.data)) ?? [],
    [sessions_query.data],
  )

  return (
    <Card className="session-navigator" size="small" title="诊断会话">
      {sessions_query.isPending && <LoadingBlock label="正在恢复会话列表" />}
      {sessions_query.isError && <ApiErrorNotice error={sessions_query.error} />}
      {sessions_query.isSuccess && sessions.length === 0 && (
        <Empty description="暂时没有 active 会话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
      {sessions.length > 0 && (
        <div className="resource-list" role="list">
          {sessions.map((session, index) => {
            const session_id = resource_optional_string(session, 'id')
            const title = resource_string(session, 'title', '未命名会话')
            const updated_at = resource_string(session, 'updated_at')
            return (
              <div key={session_id ?? index} role="listitem">
                <button
                  className="session-navigation-item"
                  disabled={!session_id}
                  onClick={() => session_id && navigate(`/workbench/sessions/${encodeURIComponent(session_id)}`)}
                  type="button"
                >
                  <span>{title}</span>
                  <small>更新于 {updated_at}</small>
                </button>
              </div>
            )
          })}
        </div>
      )}
      <LoadMoreButton
        has_more={Boolean(sessions_query.hasNextPage)}
        is_fetching={sessions_query.isFetchingNextPage}
        on_click={() => void sessions_query.fetchNextPage()}
      />
    </Card>
  )
}

function RunsPanel({
  runs,
  selected_run_id,
  pending,
  error,
  has_more,
  is_fetching,
  on_load_more,
  session_id,
}: {
  runs: unknown[]
  selected_run_id?: string
  pending: boolean
  error: unknown
  has_more: boolean
  is_fetching: boolean
  on_load_more: () => void
  session_id: string
}): ReactElement {
  const navigate = useNavigate()
  return (
    <Card className="workbench-card" size="small" title="诊断运行">
      {pending && <LoadingBlock label="正在恢复诊断运行" />}
      {error !== null && error !== undefined && <ApiErrorNotice error={error} />}
      {!pending && !error && runs.length === 0 && <Empty description="该会话尚无诊断运行" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
      {runs.length > 0 && (
        <div className="resource-list" role="list">
          {runs.map((run, index) => {
            const run_id = resource_optional_string(run, 'id')
            const status = resource_string(run, 'status', 'unknown')
            return (
              <div key={run_id ?? index} role="listitem">
                <button
                  aria-current={run_id === selected_run_id ? 'true' : undefined}
                  className="run-navigation-item"
                  disabled={!run_id}
                  onClick={() =>
                    run_id &&
                    navigate(
                      `/workbench/sessions/${encodeURIComponent(session_id)}/runs/${encodeURIComponent(run_id)}`,
                    )
                  }
                  type="button"
                >
                  <span>{run_id ?? '未知 Run'}</span>
                  <Tag color={status_color(status)}>{status}</Tag>
                </button>
              </div>
            )
          })}
        </div>
      )}
      <LoadMoreButton has_more={has_more} is_fetching={is_fetching} on_click={on_load_more} />
    </Card>
  )
}

function MessagesPanel({
  messages,
  enabled,
  pending,
  error,
  has_more,
  is_fetching,
  on_load_more,
}: {
  messages: unknown[]
  enabled: boolean
  pending: boolean
  error: unknown
  has_more: boolean
  is_fetching: boolean
  on_load_more: () => void
}): ReactElement {
  return (
    <Card className="workbench-card" size="small" title="会话消息">
      {!enabled && <Typography.Text type="secondary">等待诊断运行恢复完成后再读取会话消息。</Typography.Text>}
      {enabled && pending && <LoadingBlock label="正在恢复会话消息" />}
      {enabled && error !== null && error !== undefined && <ApiErrorNotice error={error} />}
      {enabled && !pending && !error && messages.length === 0 && <Empty description="该会话还没有消息" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
      {enabled && messages.length > 0 && (
        <Timeline
          items={messages.map((message) => ({
            content: (
              <div>
                <Space size="small">
                  <Tag color={resource_string(message, 'role') === 'user' ? 'blue' : 'purple'}>
                    {resource_string(message, 'role')}
                  </Tag>
                  <Typography.Text type="secondary">{resource_string(message, 'created_at')}</Typography.Text>
                </Space>
                <Typography.Paragraph className="message-content">
                  {resource_string(message, 'content')}
                </Typography.Paragraph>
              </div>
            ),
          }))}
        />
      )}
      <LoadMoreButton has_more={has_more} is_fetching={is_fetching} on_click={on_load_more} />
    </Card>
  )
}

function RunEventsPanel({
  events,
  error,
  has_more,
  is_fetching,
  on_load_more,
  pending,
  stream_state,
}: {
  events: PersistedRunEvent[]
  error: unknown
  has_more: boolean
  is_fetching: boolean
  on_load_more: () => void
  pending: boolean
  stream_state: 'connected' | 'connecting' | 'idle' | 'recovering'
}): ReactElement {
  const stream_message = {
    connected: '正在接收已持久化的诊断事件。',
    connecting: '正在连接持久化事件流。',
    idle: '当前 Run 已终态，不保持事件连接。',
    recovering: '事件连接中断，正在从持久化记录恢复。',
  }[stream_state]
  return (
    <Card className="workbench-card" size="small" title="诊断过程摘要">
      <Typography.Text type="secondary">{stream_message}</Typography.Text>
      {pending && <LoadingBlock label="正在恢复诊断事件" />}
      {error !== null && error !== undefined && <ApiErrorNotice error={error} />}
      {!pending && !error && events.length === 0 && (
        <Empty description="该 Run 暂无已提交的诊断事件" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
      {events.length > 0 && (
        <Timeline
          items={events.map((event) => ({
            content: (
              <div>
                <Space size="small" wrap>
                  <Tag>{event.type}</Tag>
                  <Typography.Text type="secondary">#{event.sequence}</Typography.Text>
                  <Typography.Text type="secondary">{event.occurred_at}</Typography.Text>
                </Space>
                <Typography.Paragraph className="message-content">{run_event_summary(event)}</Typography.Paragraph>
              </div>
            ),
          }))}
        />
      )}
      <LoadMoreButton has_more={has_more} is_fetching={is_fetching} on_click={on_load_more} />
    </Card>
  )
}

function SelectedRun({
  current_session_id,
  run_id,
  enabled,
}: {
  current_session_id: string
  run_id?: string
  enabled: boolean
}): ReactElement {
  const query_client = useQueryClient()
  const run_query = useQuery({ ...get_run_query(run_id ?? ''), enabled: enabled && Boolean(run_id) })
  const run = run_query.isSuccess ? (run_query.data as ApiResponse<RunResponse>).data.run : undefined
  const run_session_id = resource_optional_string(run, 'session_id')
  const run_status = resource_string(run, 'status', 'unknown')
  const run_matches_session = run_session_id === current_session_id
  const events_query = useInfiniteQuery({
    queryKey: api_v1_query_keys.run_events(run_id ?? '', { limit: API_V1_DEFAULT_PAGE_SIZE }),
    enabled: Boolean(run_id) && run_query.isSuccess && run_matches_session,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      api_v1_client.list_run_events(
        run_id ?? '',
        { cursor: pageParam, limit: API_V1_DEFAULT_PAGE_SIZE },
        { signal },
      ),
    getNextPageParam: (last_page) => {
      const page = read_page(last_page.data)
      return page.has_more ? page.next_cursor : undefined
    },
  })
  const rest_events = useMemo(
    () => events_query.data?.pages.flatMap((page) => read_items(page.data)) ?? [],
    [events_query.data],
  )
  const [events, set_events] = useState<PersistedRunEvent[]>([])

  useEffect(() => {
    if (!run_id) {
      set_events([])
      return
    }
    set_events((current_events) => merge_persisted_run_events(run_id, current_events, rest_events))
  }, [rest_events, run_id])

  const recover_persisted_events = useCallback(async (): Promise<void> => {
    if (!run_id) return
    await Promise.all([
      query_client.refetchQueries({ queryKey: api_v1_query_keys.run(run_id) }),
      query_client.refetchQueries({ queryKey: api_v1_query_keys.run_events(run_id, { limit: API_V1_DEFAULT_PAGE_SIZE }) }),
    ])
  }, [query_client, run_id])
  const refresh_terminal_run = useCallback(async (): Promise<void> => {
    if (!run_id) return
    await Promise.all([
      query_client.refetchQueries({ queryKey: api_v1_query_keys.run(run_id) }),
      query_client.refetchQueries({ queryKey: api_v1_query_keys.run_events(run_id, { limit: API_V1_DEFAULT_PAGE_SIZE }) }),
      query_client.refetchQueries({ queryKey: ['api-v1', 'session-runs', current_session_id] }),
      query_client.refetchQueries({ queryKey: ['api-v1', 'session-messages', current_session_id] }),
    ])
  }, [current_session_id, query_client, run_id])
  const stream_state = use_run_event_stream({
    enabled: Boolean(run_id) && run_matches_session && (run_status === 'queued' || run_status === 'running'),
    on_event: set_events,
    on_recover: recover_persisted_events,
    on_terminal: refresh_terminal_run,
    run_id: run_id ?? '',
  })

  if (!run_id) {
    return (
      <Card className="workbench-card" size="small" title="当前 Run">
        <Empty description="选择一个 Run 后显示状态" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    )
  }
  if (!enabled) {
    return (
      <Card className="workbench-card" size="small" title="当前 Run">
        <Typography.Text type="secondary">等待会话消息恢复完成后再读取当前 Run。</Typography.Text>
      </Card>
    )
  }
  if (run_query.isPending) return <LoadingBlock label="正在恢复当前 Run" />
  if (run_query.isError) return <ApiErrorNotice error={run_query.error} />

  if (!run_matches_session) {
    return (
      <Alert
        description="该 Run 不属于当前 Session。为避免跨会话展示，工作台没有加载其内容。"
        title="RUN_SESSION_MISMATCH"
        showIcon
        type="warning"
      />
    )
  }

  const trace_id = resource_string(run, 'trace_id')
  const result = resource_value(run, 'result')
  const error = resource_value(run, 'error')
  return (
    <>
      <Card className="workbench-card" size="small" title="当前 Run">
        <Space orientation="vertical" size="middle">
          <Space wrap>
            <Typography.Text strong>{resource_string(run, 'id')}</Typography.Text>
            <Tag color={status_color(run_status)}>{run_status}</Tag>
          </Space>
          <Typography.Paragraph>
            <strong>Trace：</strong>
            {trace_id}
          </Typography.Paragraph>
          {result !== null && result !== undefined && (
            <Alert
              description="结构化结果已由服务端持久化；P3.4 才提供根因、证据、影响、建议和风险的结果卡。"
              title="结构化结果待展示"
              showIcon
              type="info"
            />
          )}
          {error !== null && error !== undefined && (
            <Alert description="服务端返回了安全 Run 错误。" title="诊断运行返回安全错误" showIcon type="error" />
          )}
        </Space>
      </Card>
      <RunEventsPanel
        error={events_query.error}
        events={events}
        has_more={Boolean(events_query.hasNextPage)}
        is_fetching={events_query.isFetchingNextPage}
        on_load_more={() => void events_query.fetchNextPage()}
        pending={events_query.isPending}
        stream_state={stream_state}
      />
    </>
  )
}

function SessionWorkspace({ session_id, run_id }: { session_id: string; run_id?: string }): ReactElement {
  const navigate = useNavigate()
  const session_query = useQuery({ ...get_session_query(session_id), enabled: Boolean(session_id) })
  const runs_query = useInfiniteQuery({
    queryKey: api_v1_query_keys.session_runs(session_id, { limit: API_V1_DEFAULT_PAGE_SIZE }),
    enabled: session_query.isSuccess,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      api_v1_client.list_session_runs(session_id, { cursor: pageParam, limit: API_V1_DEFAULT_PAGE_SIZE }, { signal }),
    getNextPageParam: (last_page) => {
      const page = read_page(last_page.data)
      return page.has_more ? page.next_cursor : undefined
    },
  })
  const messages_query = useInfiniteQuery({
    queryKey: api_v1_query_keys.session_messages(session_id, { limit: API_V1_DEFAULT_PAGE_SIZE }),
    enabled: runs_query.isSuccess,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) =>
      api_v1_client.list_session_messages(
        session_id,
        { cursor: pageParam, limit: API_V1_DEFAULT_PAGE_SIZE },
        { signal },
      ),
    getNextPageParam: (last_page) => {
      const page = read_page(last_page.data)
      return page.has_more ? page.next_cursor : undefined
    },
  })
  const recovered_runs = useMemo(
    () => runs_query.data?.pages.flatMap((page) => read_items(page.data)) ?? [],
    [runs_query.data],
  )
  const recovered_messages = useMemo(
    () => messages_query.data?.pages.flatMap((page) => read_items(page.data)) ?? [],
    [messages_query.data],
  )

  useEffect(() => {
    if (run_id || !messages_query.isSuccess) return
    const first_run_id = resource_optional_string(recovered_runs[0], 'id')
    if (first_run_id) {
      navigate(`/workbench/sessions/${encodeURIComponent(session_id)}/runs/${encodeURIComponent(first_run_id)}`, {
        replace: true,
      })
    }
  }, [messages_query.isSuccess, navigate, recovered_runs, run_id, session_id])

  if (session_query.isPending) return <LoadingBlock label="正在恢复诊断会话" />
  if (session_query.isError) {
    return (
      <section className="workbench-page" aria-labelledby="workbench-title">
        <Typography.Title id="workbench-title" level={2}>无法恢复诊断会话</Typography.Title>
        <ApiErrorNotice error={session_query.error} />
        <Button className="return-workbench" onClick={() => navigate('/workbench')} type="link">返回会话列表</Button>
      </section>
    )
  }

  const session = (session_query.data as ApiResponse<SessionResponse>).data.session
  const session_status = resource_string(session, 'status', 'unknown')
  return (
    <section className="workbench-page" aria-labelledby="workbench-title">
      <div className="page-eyebrow">SESSION RECOVERY</div>
      <Space align="center" className="workbench-title-row" wrap>
        <Typography.Title id="workbench-title" level={2}>{resource_string(session, 'title', '诊断会话')}</Typography.Title>
        <Tag color={status_color(session_status)}>{session_status}</Tag>
      </Space>
      <Typography.Paragraph className="page-description">
        已按 Session → Runs → Message → 选定 Run 的顺序从服务端恢复。时间均保留服务端 UTC 字符串；可在 active 会话受理一条新的诊断运行。
      </Typography.Paragraph>
      {session_status === 'archived' && (
        <Alert className="archive-notice" description="会话已归档，仅可读取历史消息和诊断运行；重新激活或编辑待后续产品切片。" title="已归档会话" showIcon type="info" />
      )}
      <RunSubmissionPanel session_id={session_id} session_status={session_status} />
      <div className="session-workspace-grid">
        <div className="session-workspace-column">
          <RunsPanel
            error={runs_query.error}
            has_more={Boolean(runs_query.hasNextPage)}
            is_fetching={runs_query.isFetchingNextPage}
            on_load_more={() => void runs_query.fetchNextPage()}
            pending={runs_query.isPending}
            runs={recovered_runs}
            selected_run_id={run_id}
            session_id={session_id}
          />
          <MessagesPanel
            enabled={runs_query.isSuccess}
            error={messages_query.error}
            has_more={Boolean(messages_query.hasNextPage)}
            is_fetching={messages_query.isFetchingNextPage}
            on_load_more={() => void messages_query.fetchNextPage()}
            messages={recovered_messages}
            pending={messages_query.isPending}
          />
        </div>
        <SelectedRun current_session_id={session_id} enabled={messages_query.isSuccess} run_id={run_id} />
      </div>
    </section>
  )
}

export function WorkbenchPage(): ReactElement {
  const { session_id, run_id } = useParams<{ session_id: string; run_id: string }>()
  if (session_id) return <SessionWorkspace run_id={run_id} session_id={session_id} />

  return (
    <section className="workbench-page" aria-labelledby="workbench-title">
      <div className="page-eyebrow">OPERATIONS DIAGNOSIS</div>
      <Typography.Title id="workbench-title" level={2}>诊断工作台</Typography.Title>
      <Typography.Paragraph className="page-description">
        从持久化 Session 恢复诊断上下文。选择会话后，工作台只读取 v1 API 的 Session、Run 与 Message。
      </Typography.Paragraph>
      <SessionNavigator />
    </section>
  )
}
