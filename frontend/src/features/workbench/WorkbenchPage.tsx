import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Collapse,
  Empty,
  Skeleton,
  Space,
  Tag,
  Typography,
} from 'antd'
import type { ReactElement, ReactNode } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import {
  API_V1_DEFAULT_PAGE_SIZE,
  ApiClientError,
  api_v1_client,
  type ApiResponse,
  type DiagnosisRunListResponse,
  type MessageListResponse,
  type SessionResponse,
} from '../../api/v1/client'
import { api_v1_query_keys, create_run_mutation, get_session_query, list_run_events_query } from '../../api/v1/queries'
import {
  investigation_status_color,
  investigation_status_text,
  project_conversation_turns,
  type ConversationInvestigation,
  type ConversationMessage,
  type ConversationTurn,
} from './conversation-turns'
import { DiagnosisResultPanel } from './DiagnosisResultPanel'
import { merge_persisted_run_events, run_event_summary, type PersistedRunEvent } from './run-events'
import { use_run_event_stream } from './use-run-event-stream'
import { read_diagnosis_result } from './result-readers'
import {
  clear_session_run_send_intent,
  create_session_run_send_intent,
  load_session_run_send_intent,
  mark_session_run_send_intent_accepted,
  save_session_run_send_intent,
  type SessionRunSendIntent,
} from './send-intent'
import {
  read_items,
  read_page,
  read_record,
  resource_optional_string,
  resource_string,
} from './resource-readers'

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

  if (error instanceof Error) {
    return { title: error.message, detail: '页面没有用本地数据替代服务端事实；请重新恢复或按提示处理。' }
  }

  return { title: '暂时无法读取服务数据。', detail: '请稍后刷新；页面不会使用本地数据代替服务端事实。' }
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

function is_idempotency_key_conflict(error: unknown): boolean {
  return error instanceof ApiClientError && error.code === 'IDEMPOTENCY_KEY_REUSED'
}

function is_validation_error(error: unknown): boolean {
  return error instanceof ApiClientError && error.code === 'VALIDATION_ERROR'
}

function session_storage(): Storage | undefined {
  try {
    return window.sessionStorage
  } catch {
    return undefined
  }
}

async function fetch_all_pages<TData>(
  fetch_page: (cursor: string | undefined) => Promise<ApiResponse<TData>>,
): Promise<{ pageParams: (string | undefined)[]; pages: ApiResponse<TData>[] }> {
  const page_params: (string | undefined)[] = []
  const pages: ApiResponse<TData>[] = []
  const seen_cursors = new Set<string>()
  let cursor: string | undefined

  do {
    const page = await fetch_page(cursor)
    page_params.push(cursor)
    pages.push(page)
    const page_info = read_page(page.data)
    if (!page_info.has_more || !page_info.next_cursor || seen_cursors.has(page_info.next_cursor)) break
    seen_cursors.add(page_info.next_cursor)
    cursor = page_info.next_cursor
  } while (true)

  return { pageParams: page_params, pages }
}

function LoadMoreButton({
  has_more,
  is_fetching,
  label,
  on_click,
}: {
  has_more: boolean
  is_fetching: boolean
  label: string
  on_click: () => void
}): ReactElement | null {
  if (!has_more) return null
  return (
    <Button className="load-more-button" disabled={is_fetching} onClick={on_click} type="link">
      {is_fetching ? '正在加载…' : label}
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
    <Card className="session-navigator" size="small" title="你的会话">
      <Typography.Paragraph type="secondary">
        会话会保存问题、调查过程和后续答复。进入 active 会话可发起调查；新建会话与普通聊天仍在后续切片。
      </Typography.Paragraph>
      {sessions_query.isPending && <LoadingBlock label="正在恢复会话列表" />}
      {sessions_query.isError && <ApiErrorNotice error={sessions_query.error} />}
      {sessions_query.isSuccess && sessions.length === 0 && (
        <Empty description="暂时没有活跃会话" image={Empty.PRESENTED_IMAGE_SIMPLE} />
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
                  <small>最近更新 {updated_at}</small>
                </button>
              </div>
            )
          })}
        </div>
      )}
      <LoadMoreButton
        has_more={Boolean(sessions_query.hasNextPage)}
        is_fetching={sessions_query.isFetchingNextPage}
        label="加载更多会话"
        on_click={() => void sessions_query.fetchNextPage()}
      />
    </Card>
  )
}

function role_label(role: unknown): string | undefined {
  if (role === 'db') return '数据库'
  if (role === 'log') return '日志'
  if (role === 'server') return '服务'
  return undefined
}

function event_duration_text(event: PersistedRunEvent): string | undefined {
  const duration_ms = event.data.duration_ms
  if (typeof duration_ms !== 'number' || !Number.isSafeInteger(duration_ms) || duration_ms < 0) return undefined
  return `${duration_ms} ms`
}

function InvestigationProcess({ investigation, session_id }: { investigation: ConversationInvestigation; session_id: string }): ReactElement {
  const query_client = useQueryClient()
  const [events, set_events] = useState<PersistedRunEvent[]>([])
  const events_query = useQuery({
    ...list_run_events_query(investigation.id, { limit: 100 }),
    enabled: Boolean(investigation.id),
    refetchInterval: investigation.status === 'queued' || investigation.status === 'running' ? 1500 : false,
  })

  useEffect(() => {
    if (!events_query.isSuccess) return
    set_events((current_events) => merge_persisted_run_events(investigation.id, current_events, read_items(events_query.data.data)))
  }, [events_query.data, events_query.isSuccess, investigation.id])

  const recover = useCallback(async (): Promise<void> => {
    const response = await api_v1_client.list_run_events(investigation.id, { limit: 100 })
    set_events((current_events) => merge_persisted_run_events(investigation.id, current_events, read_items(response.data)))
  }, [investigation.id])
  const on_terminal = useCallback(async (): Promise<void> => {
    await Promise.all([
      query_client.invalidateQueries({ queryKey: api_v1_query_keys.session_runs(session_id, { limit: API_V1_DEFAULT_PAGE_SIZE }) }),
      query_client.invalidateQueries({ queryKey: api_v1_query_keys.session_messages(session_id, { limit: API_V1_DEFAULT_PAGE_SIZE }) }),
    ])
  }, [query_client, session_id])
  const stream_state = use_run_event_stream({
    enabled: investigation.status === 'queued' || investigation.status === 'running',
    on_event: set_events,
    on_recover: recover,
    on_terminal,
    run_id: investigation.id,
  })

  const visible_events = events.filter((event) => event.type === 'agent_start' || event.type === 'agent_done' || event.type === 'route_decided')
  return (
    <div className="investigation-process" aria-label="调查过程">
      <Space align="center" size="small" wrap>
        <Typography.Text strong>只读调查过程</Typography.Text>
        <Tag color={stream_state === 'connected' ? 'blue' : 'default'}>{stream_state === 'connected' ? '实时更新' : '已保存事件'}</Tag>
      </Space>
      {visible_events.length === 0 ? (
        <Typography.Text type="secondary">正在等待服务端写入可展示的调查过程。</Typography.Text>
      ) : (
        <div className="investigation-process-events">
          {visible_events.map((event) => {
            const role = role_label(event.data.role)
            const duration = event_duration_text(event)
            return (
              <div className="investigation-process-event" key={event.id}>
                {role && <Tag color={event.type === 'agent_done' ? 'green' : 'blue'}>{role}</Tag>}
                <Typography.Text>{run_event_summary(event)}</Typography.Text>
                {duration && <Typography.Text type="secondary">{duration}</Typography.Text>}
              </div>
            )
          })}
        </div>
      )}
      {events_query.isError && <Typography.Text type="secondary">过程事件暂不可读取；不会以本地内容替代服务端事实。</Typography.Text>}
    </div>
  )
}
function AssistantReply({ investigation, output, session_id }: { investigation: ConversationInvestigation; output?: ConversationMessage; session_id: string }): ReactElement {
  if (investigation.status === 'succeeded') {
    const result_read = investigation.result === null
      ? { issues: [{ field: 'result', message: '成功调查缺少结构化结果。' }] }
      : read_diagnosis_result(investigation.result, investigation.id)

    if (!output) {
      return (
        <Alert
          description="服务端已标记调查成功，但尚未恢复关联的助手答复。页面不会根据 Result 伪造一条已保存消息。"
          title="ANSWER_RECOVERY_PENDING"
          showIcon
          type="warning"
        />
      )
    }

    const first_issue = result_read.issues[0]
    return (
      <div className="conversation-message conversation-message-assistant" aria-label="助手答复">
        <div className="conversation-message-meta">
          <Tag color="purple">OperMind</Tag>
          <Typography.Text type="secondary">{output.created_at}</Typography.Text>
        </div>
        <Typography.Paragraph className="conversation-message-content">{output.content}</Typography.Paragraph>
        {result_read.result ? (
          <Collapse
            className="investigation-details"
            items={[{
              key: 'result',
              label: '展开结论、证据与建议',
              children: <DiagnosisResultPanel result={result_read.result} />,
            }]}
          />
        ) : (
          <Alert
            description={first_issue ? `${first_issue.field}：${first_issue.message}` : '结构化结果不符合公开契约。'}
            title="RESULT_PROTOCOL_ERROR"
            showIcon
            type="warning"
          />
        )}
      </div>
    )
  }

  if (investigation.status === 'failed') {
    const error_record = investigation.error as Record<string, unknown> | null
    const code = typeof error_record?.code === 'string' ? error_record.code : undefined
    const message = typeof error_record?.message === 'string' ? error_record.message : undefined
    return (
      <Alert
        description={code && message ? message : '服务端未返回可安全展示的调查错误。'}
        title={code ?? '调查未完成'}
        showIcon
        type="error"
      />
    )
  }

  if (investigation.status === 'cancelled') {
    return <Alert description="可保留已保存的会话内容；当前不推断取消原因或继续执行。" title="调查已取消" showIcon type="warning" />
  }

  return (
    <Space direction="vertical" size="small" style={{ width: '100%' }}>
      <Alert
        description={investigation.status === 'queued' ? '请求已保存，正在等待调查开始。' : '正在并行收集数据库、日志和服务的只读证据。'}
        title={investigation.status === 'queued' ? '正在准备调查' : '正在调查'}
        showIcon
        type="info"
      />
      <InvestigationProcess investigation={investigation} session_id={session_id} />
    </Space>
  )
}

function InvestigationSummary({ investigation, output, session_id }: { investigation?: ConversationInvestigation; output?: ConversationMessage; session_id: string }): ReactElement {
  if (!investigation) {
    return (
      <div className="investigation-summary investigation-summary-empty">
        <Typography.Text type="secondary">这条消息尚未关联已保存的调查；页面不会创建或猜测调查记录。</Typography.Text>
      </div>
    )
  }

  return (
    <div className="investigation-summary" aria-label="调查摘要">
      <Space align="center" wrap>
        <Typography.Text strong>调查摘要</Typography.Text>
        <Tag color={investigation_status_color(investigation.status)}>{investigation_status_text(investigation.status)}</Tag>
      </Space>
      <AssistantReply investigation={investigation} output={output} session_id={session_id} />
    </div>
  )
}

function ConversationTurnCard({ turn, session_id }: { turn: ConversationTurn; session_id: string }): ReactElement {
  return (
    <article className="conversation-turn">
      <div className="conversation-message conversation-message-user" aria-label="用户问题">
        <div className="conversation-message-meta">
          <Tag color="blue">你</Tag>
          <Typography.Text type="secondary">{turn.input.created_at}</Typography.Text>
        </div>
        <Typography.Paragraph className="conversation-message-content">{turn.input.content}</Typography.Paragraph>
      </div>
      <InvestigationSummary investigation={turn.investigation} output={turn.output} session_id={session_id} />
    </article>
  )
}

function ConversationTimeline({ messages, runs, session_id }: { messages: unknown[]; runs: unknown[]; session_id: string }): ReactElement {
  const { issues, timeline } = useMemo(
    () => project_conversation_turns(messages, runs, session_id),
    [messages, runs, session_id],
  )

  return (
    <Card className="conversation-card" size="small" title="对话">
      {issues.map((issue, index) => (
        <Alert className="conversation-protocol-notice" description={issue} key={`${issue}-${index}`} showIcon title="会话关联异常" type="warning" />
      ))}
      {timeline.length === 0 && (
        <Empty description="该会话还没有可恢复的对话内容" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      )}
      <div className="conversation-timeline">
        {timeline.map((item) => {
          if (item.kind === 'system') {
            return (
              <Alert
                className="conversation-system-message"
                description={item.message.content}
                key={item.message.id}
                title={`系统提醒 · ${item.message.created_at}`}
                showIcon
                type="info"
              />
            )
          }
          return <ConversationTurnCard key={item.turn.input.id} session_id={session_id} turn={item.turn} />
        })}
      </div>
    </Card>
  )
}

function SessionWorkspace({ session_id }: { session_id: string }): ReactElement {
  const navigate = useNavigate()
  const query_client = useQueryClient()
  const storage = session_storage()
  const [query, set_query] = useState('')
  const [send_intent, set_send_intent] = useState<SessionRunSendIntent | undefined>(() =>
    storage ? load_session_run_send_intent(storage, session_id) : undefined,
  )
  const [recovery_error, set_recovery_error] = useState<unknown>()
  const automatic_recovery_attempts = useRef(new Set<string>())
  const session_query = useQuery({ ...get_session_query(session_id), enabled: Boolean(session_id) })
  const runs_query_key = api_v1_query_keys.session_runs(session_id, { limit: API_V1_DEFAULT_PAGE_SIZE })
  const messages_query_key = api_v1_query_keys.session_messages(session_id, { limit: API_V1_DEFAULT_PAGE_SIZE })
  const runs_query = useInfiniteQuery({
    queryKey: runs_query_key,
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
    queryKey: messages_query_key,
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
    const restored = storage ? load_session_run_send_intent(storage, session_id) : undefined
    set_send_intent(restored)
    set_query(restored?.query ?? '')
    set_recovery_error(undefined)
  }, [session_id, storage])

  const reconcile_accepted_intent = async (intent: SessionRunSendIntent): Promise<void> => {
    if (!intent.accepted_run_id || !intent.input_message_id) return
    set_recovery_error(undefined)
    const all_runs = await fetch_all_pages<DiagnosisRunListResponse>((cursor) =>
      api_v1_client.list_session_runs(session_id, { cursor, limit: API_V1_DEFAULT_PAGE_SIZE }),
    )
    const all_messages = await fetch_all_pages<MessageListResponse>((cursor) =>
      api_v1_client.list_session_messages(session_id, { cursor, limit: API_V1_DEFAULT_PAGE_SIZE }),
    )
    query_client.setQueryData(runs_query_key, all_runs)
    query_client.setQueryData(messages_query_key, all_messages)

    const accepted_run_found = all_runs.pages
      .flatMap((page) => read_items(page.data))
      .some((run) => resource_optional_string(run, 'id') === intent.accepted_run_id
        && resource_optional_string(run, 'session_id') === session_id
        && resource_optional_string(run, 'input_message_id') === intent.input_message_id)
    const input_message_found = all_messages.pages
      .flatMap((page) => read_items(page.data))
      .some((message) => resource_optional_string(message, 'id') === intent.input_message_id
        && resource_optional_string(message, 'session_id') === session_id
        && resource_string(message, 'role') === 'user')

    if (!accepted_run_found || !input_message_found) {
      throw new Error('ACCEPTED_TURN_NOT_FOUND：调查已受理，但尚未恢复对应的已保存问题或调查记录。')
    }

    if (storage) clear_session_run_send_intent(storage, session_id)
    set_send_intent(undefined)
    set_query('')
  }

  const create_run = useMutation({
    ...create_run_mutation(),
    onSuccess: async (response, variables) => {
      const accepted_run = read_record(response.data.run)
      const accepted_run_id = resource_optional_string(accepted_run, 'id')
      const accepted_session_id = resource_optional_string(accepted_run, 'session_id')
      const input_message_id = resource_optional_string(accepted_run, 'input_message_id')
      const current_intent = storage ? load_session_run_send_intent(storage, session_id) : undefined
      if (!current_intent || current_intent.idempotency_key !== variables.idempotency_key) {
        set_recovery_error(new Error('SEND_INTENT_MISSING：无法确认当前受理响应对应的发送意图。'))
        return
      }
      if (accepted_session_id !== session_id || !accepted_run_id || !input_message_id) {
        set_recovery_error(new Error('ACCEPT_RESPONSE_PROTOCOL_ERROR：服务端受理响应未返回当前会话的合法 Run。'))
        return
      }

      const accepted_intent = mark_session_run_send_intent_accepted(current_intent, accepted_run_id, input_message_id)
      if (storage) save_session_run_send_intent(storage, accepted_intent)
      set_send_intent(accepted_intent)
    },
    onError: (error) => {
      if (is_validation_error(error)) {
        if (storage) clear_session_run_send_intent(storage, session_id)
        set_send_intent(undefined)
      }
      if (error instanceof ApiClientError && error.code === 'SESSION_ARCHIVED') {
        void query_client.invalidateQueries({ queryKey: api_v1_query_keys.session(session_id) })
      }
      set_recovery_error(error)
    },
  })

  useEffect(() => {
    if (!session_query.isSuccess || !send_intent?.accepted_run_id || !send_intent.input_message_id || create_run.isPending) return
    const attempt_key = `${session_id}:${send_intent.accepted_run_id}`
    if (automatic_recovery_attempts.current.has(attempt_key)) return
    automatic_recovery_attempts.current.add(attempt_key)
    void reconcile_accepted_intent(send_intent).catch(set_recovery_error)
  }, [create_run.isPending, send_intent, session_id, session_query.isSuccess])

  const discard_send_intent = (): void => {
    if (storage) clear_session_run_send_intent(storage, session_id)
    set_send_intent(undefined)
    set_recovery_error(undefined)
  }

  const submit_investigation = (): void => {
    if (create_run.isPending || !storage) return
    const normalized_query = query.trim()
    if (!normalized_query) {
      set_recovery_error(new Error('调查问题不能为空。'))
      return
    }

    const current_intent = send_intent ?? create_session_run_send_intent(session_id, normalized_query)
    if (current_intent.query !== normalized_query) {
      set_recovery_error(new Error('当前发送意图仍在恢复中；请先完成重试或明确刷新后再修改问题。'))
      return
    }
    save_session_run_send_intent(storage, current_intent)
    set_send_intent(current_intent)
    set_recovery_error(undefined)
    create_run.mutate({
      idempotency_key: current_intent.idempotency_key,
      query: current_intent.query,
      session_id,
    })
  }

  const retry_recovery = (): void => {
    if (!send_intent?.accepted_run_id || !send_intent.input_message_id || create_run.isPending) return
    void reconcile_accepted_intent(send_intent).catch(set_recovery_error)
  }

  if (session_query.isPending) return <LoadingBlock label="正在恢复会话" />
  if (session_query.isError) {
    return (
      <section className="workbench-page" aria-labelledby="workbench-title">
        <Typography.Title id="workbench-title" level={2}>无法恢复会话</Typography.Title>
        <ApiErrorNotice error={session_query.error} />
        <Button className="return-workbench" onClick={() => navigate('/workbench')} type="link">返回会话列表</Button>
      </section>
    )
  }

  const session = (session_query.data as ApiResponse<SessionResponse>).data.session
  const session_status = resource_string(session, 'status', 'unknown')
  const can_send = session_status === 'active'
  const has_idempotency_key_conflict = is_idempotency_key_conflict(recovery_error)
  return (
    <section className="workbench-page" aria-labelledby="workbench-title">
      <div className="page-eyebrow">PERSONAL CONVERSATION · INVESTIGATION</div>
      <Space align="center" className="workbench-title-row" wrap>
        <Typography.Title id="workbench-title" level={2}>{resource_string(session, 'title', '个人会话')}</Typography.Title>
        <Tag color={status_color(session_status)}>{session_status}</Tag>
      </Space>
      <Typography.Paragraph className="page-description">
        这里按对话阅读已保存的问题、调查和助手答复。每次提交都会创建一次运维调查，不提供普通聊天或自动处理。
      </Typography.Paragraph>
      {session_status === 'archived' && (
        <Alert className="archive-notice" description="会话已归档，仅可阅读历史内容；重新激活和编辑尚未实现。" title="已归档会话" showIcon type="info" />
      )}
      {can_send && (
        <Card className="investigation-composer" size="small" title="发起调查">
          <Typography.Paragraph type="secondary">
            每次提问都会创建一次运维调查。问题会先由服务端持久化；页面不会把本地输入伪造成已保存消息。
          </Typography.Paragraph>
          <textarea
            aria-label="调查问题"
            className="investigation-input"
            disabled={create_run.isPending || Boolean(send_intent) || has_idempotency_key_conflict}
            onChange={(event) => {
              set_query(event.target.value)
              if (is_validation_error(recovery_error)) set_recovery_error(undefined)
            }}
            placeholder="例如：订单服务变慢，帮我排查慢查询。"
            value={query}
          />
          <Space className="investigation-composer-actions" wrap>
            <Button
              disabled={create_run.isPending || Boolean(send_intent?.accepted_run_id) || has_idempotency_key_conflict}
              loading={create_run.isPending}
              onClick={submit_investigation}
              type="primary"
            >
              {send_intent?.phase === 'acceptance_unknown' ? '用相同请求重试' : '开始调查'}
            </Button>
            {send_intent?.accepted_run_id && (
              <Button onClick={retry_recovery} type="default">重新恢复已保存内容</Button>
            )}
            {has_idempotency_key_conflict && (
              <Button onClick={discard_send_intent} type="default">丢弃当前发送意图</Button>
            )}
          </Space>
          {send_intent?.phase === 'acceptance_unknown' && (
            <Alert
              className="investigation-send-notice"
              description="本次请求的受理结果尚未确认。请使用同一问题和同一幂等键重试，或刷新页面恢复；不要修改问题后盲目再次发送。"
              title="等待确认调查是否已受理"
              showIcon
              type="warning"
            />
          )}
          {send_intent?.phase === 'accepted' && (
            <Alert
              className="investigation-send-notice"
              description="调查已受理，正在按已保存的 Run 与 Message 对账。完成前不会显示本地伪造的问题。"
              title="正在恢复已保存的调查"
              showIcon
              type="info"
            />
          )}
          {recovery_error !== undefined && <ApiErrorNotice error={recovery_error} />}
        </Card>
      )}
      {runs_query.isPending && <LoadingBlock label="正在恢复关联调查" />}
      {runs_query.isError && <ApiErrorNotice error={runs_query.error} />}
      {runs_query.isSuccess && messages_query.isPending && <LoadingBlock label="正在恢复会话消息" />}
      {runs_query.isSuccess && messages_query.isError && <ApiErrorNotice error={messages_query.error} />}
      {runs_query.isSuccess && messages_query.isSuccess && (
        <>
          <ConversationTimeline messages={recovered_messages} runs={recovered_runs} session_id={session_id} />
          <LoadMoreButton
            has_more={Boolean(runs_query.hasNextPage)}
            is_fetching={runs_query.isFetchingNextPage}
            label="加载更多关联调查"
            on_click={() => void runs_query.fetchNextPage()}
          />
          <LoadMoreButton
            has_more={Boolean(messages_query.hasNextPage)}
            is_fetching={messages_query.isFetchingNextPage}
            label="加载更多已保存消息"
            on_click={() => void messages_query.fetchNextPage()}
          />
          <Typography.Paragraph className="conversation-history-boundary" type="secondary">
            当前按服务端正序 cursor 读取已保存消息和关联调查；尚未实现“最近优先、向前加载历史”的新契约。
          </Typography.Paragraph>
        </>
      )}
    </section>
  )
}

export function WorkbenchPage(): ReactElement {
  const { session_id } = useParams<{ session_id: string }>()
  if (session_id) return <SessionWorkspace session_id={session_id} />

  return (
    <section className="workbench-page" aria-labelledby="workbench-title">
      <div className="page-eyebrow">OPERATIONS COPILOT</div>
      <Typography.Title id="workbench-title" level={2}>我的会话</Typography.Title>
      <Typography.Paragraph className="page-description">
        从已保存会话恢复受控运维调查。当前产品先支持订单慢查询的只读排查，不伪造监控、修复或普通聊天能力。
      </Typography.Paragraph>
      <SessionNavigator />
    </section>
  )
}
