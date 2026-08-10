import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ReactElement, ReactNode } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'

import {
  API_V1_DEFAULT_PAGE_SIZE,
  ApiClientError,
  api_v1_client,
  type ApiResponse,
  type DiagnosisRunListResponse,
  type MessageListResponse,
  type SessionResponse,
} from '../../api/v1/client'
import {
  api_v1_query_keys,
  cancel_run_mutation,
  create_run_mutation,
  create_session_mutation,
  default_session_list_query,
  get_session_query,
  list_run_events_query,
  list_services_query,
  send_plain_message_mutation,
} from '../../api/v1/queries'
import {
  investigation_status_text,
  project_conversation_turns,
  type ConversationInvestigation,
  type ConversationMessage,
  type ConversationTurn,
} from './conversation-turns'
import { ActionProposalPanel } from './ActionProposalPanel'
import { DiagnosisResultPanel } from './DiagnosisResultPanel'
import { is_investigation_message } from './message-intent'
import {
  clear_pending_plain_message,
  load_pending_plain_message,
  save_pending_plain_message,
} from './plain-message-intent'
import { Composer } from '../shell/Composer'
import { WelcomePanel } from '../shell/WelcomePanel'
import { TraceCard } from './TraceCard'
import { merge_persisted_run_events, type PersistedRunEvent } from './run-events'
import { use_run_event_stream } from './use-run-event-stream'
import { read_diagnosis_result } from './result-readers'
import {
  clear_session_run_send_intent,
  create_session_run_send_intent,
  load_session_run_send_intent,
  mark_session_run_send_intent_accepted,
  save_session_run_send_intent,
  submit_unaccepted_session_runs,
  type SessionRunSendIntent,
} from './send-intent'
import {
  read_items,
  read_page,
  read_record,
  resource_optional_string,
  resource_string,
} from './resource-readers'
import {
  UiAlert,
  UiButton,
  UiCollapse,
  UiSkeleton,
  UiSpace,
  UiTag,
  UiText,
  UiTitle,
} from './ui'

function safe_error(error: unknown): { title: string; detail: ReactNode } {
  if (error instanceof ApiClientError) {
    const request_id = error.diagnostics.meta_request_id ?? error.diagnostics.response_request_id
    const trace_id = error.diagnostics.meta_trace_id ?? error.diagnostics.response_trace_id
    return {
      title: `${error.code}：${error.message}`,
      detail: (
        <UiSpace size="small" wrap>
          {request_id && <UiTag>请求 {request_id}</UiTag>}
          {trace_id && <UiTag color="cyan">Trace {trace_id}</UiTag>}
        </UiSpace>
      ),
    }
  }

  if (error instanceof Error) {
    return { title: error.message, detail: '页面没有用本地数据替代服务端事实；请重新恢复或按提示处理。' }
  }

  return { title: '暂时无法读取服务数据。', detail: '请稍后刷新；页面不会使用本地数据代替服务端事实。' }
}

function LoadingBlock({ label }: { label: string }): ReactElement {
  return (
    <div aria-label={label} className="workbench-loading">
      <UiSkeleton active paragraph={{ rows: 4 }} title />
    </div>
  )
}

function ApiErrorNotice({ error }: { error: unknown }): ReactElement {
  const safe = safe_error(error)
  return <UiAlert description={safe.detail} showIcon title={safe.title} type="error" />
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

function session_service_ids(value: unknown): string[] {
  const record = read_record(value)
  const service_ids = record?.service_ids
  if (Array.isArray(service_ids)) return service_ids.filter((id): id is string => typeof id === 'string')
  const service_id = resource_optional_string(value, 'service_id')
  return service_id ? [service_id] : []
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
    <UiButton className="load-more-button" disabled={is_fetching} onClick={on_click} type="link">
      {is_fetching ? '正在加载…' : label}
    </UiButton>
  )
}

function InvestigationProcess({ investigation, session_id }: { investigation: ConversationInvestigation; session_id: string }): ReactElement {
  const query_client = useQueryClient()
  const [events, set_events] = useState<PersistedRunEvent[]>([])
  const [cancel_error, set_cancel_error] = useState<unknown>()
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
  const cancel_mutation = useMutation({
    ...cancel_run_mutation(),
    onSuccess: () => void on_terminal(),
    onError: set_cancel_error,
  })
  const stream_state = use_run_event_stream({
    enabled: investigation.status === 'queued' || investigation.status === 'running',
    on_event: set_events,
    on_recover: recover,
    on_terminal,
    run_id: investigation.id,
  })
  const is_live = investigation.status === 'queued' || investigation.status === 'running' || stream_state === 'connected'

  return (
    <div className="investigation-process">
      <TraceCard
        events={events}
        running={is_live}
      />
      {is_live && (
        <UiSpace wrap className="investigation-process-actions">
          <UiButton danger disabled={cancel_mutation.isPending} loading={cancel_mutation.isPending} onClick={() => cancel_mutation.mutate(investigation.id)}>
            停止调查
          </UiButton>
        </UiSpace>
      )}
      {cancel_mutation.isError && <UiAlert description={safe_error(cancel_error).title} showIcon title="停止调查未完成" type="error" />}
    </div>
  )
}
function AssistantReply({ investigation, output, session_id }: { investigation: ConversationInvestigation; output?: ConversationMessage; session_id: string }): ReactElement {
  if (investigation.status === 'succeeded') {
    const result_read = investigation.result === null
      ? { issues: [{ field: 'result', message: '成功调查缺少结构化结果。' }] }
      : read_diagnosis_result(investigation.result, investigation.id)

    return (
      <div className="message-body">
        <div className="message-label">OperMind · {investigation_status_text(investigation.status)}</div>
        <div className="assistant-meta">
          <span className="meta-pill readonly"><span className="mini-dot" />只读调查</span>
          <span className="meta-pill blue">工具调用</span>
          {output && <span>{output.created_at}</span>}
        </div>
        <InvestigationProcess investigation={investigation} session_id={session_id} />
        {output && <div className="bubble">{output.content}</div>}
        {!output && (
          <UiAlert
            description="服务端已标记调查成功，但尚未恢复关联的助手答复。页面不会根据 Result 伪造一条已保存消息。"
            showIcon
            title="ANSWER_RECOVERY_PENDING"
            type="warning"
          />
        )}
        {result_read.result ? (
          <UiCollapse
            className="investigation-details"
            items={[{
              key: 'result',
              label: '展开结论、证据与建议',
              children: <UiSpace direction="vertical" size="middle" style={{ width: '100%' }}><DiagnosisResultPanel result={result_read.result} /><ActionProposalPanel run_id={investigation.id} /></UiSpace>,
            }]}
          />
        ) : (
          <UiAlert
            description={result_read.issues[0] ? `${result_read.issues[0].field}：${result_read.issues[0].message}` : '结构化结果不符合公开契约。'}
            showIcon
            title="RESULT_PROTOCOL_ERROR"
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
      <div className="message-body">
        <div className="message-label">OperMind · 调查未完成</div>
        <UiAlert
          description={code && message ? message : '服务端未返回可安全展示的调查错误。'}
          showIcon
          title={code ?? '调查未完成'}
          type="error"
        />
        <InvestigationProcess investigation={investigation} session_id={session_id} />
      </div>
    )
  }

  if (investigation.status === 'cancelled') {
    return (
      <div className="message-body">
        <div className="message-label">OperMind · 调查已取消</div>
        <UiAlert description="可保留已保存的会话内容；当前不推断取消原因或继续执行。" showIcon title="调查已取消" type="warning" />
      </div>
    )
  }

  return (
    <div className="message-body">
      <div className="message-label">OperMind · {investigation_status_text(investigation.status)}</div>
      <div className="assistant-meta">
        <span className="meta-pill readonly"><span className="mini-dot" />只读调查</span>
        <span className="meta-pill blue">工具调用中</span>
      </div>
      <InvestigationProcess investigation={investigation} session_id={session_id} />
    </div>
  )
}

function service_result_title(service_id: string | undefined, services_by_id: Map<string, { kind?: string; title?: string }>): string {
  if (!service_id) return '未关联服务'
  const service = services_by_id.get(service_id)
  if (!service) return service_id
  return service.kind ? `${service.title ?? service_id} · ${service.kind}` : service.title ?? service_id
}

function ConversationTurnCard({ turn, session_id, services_by_id }: { turn: ConversationTurn; session_id: string; services_by_id: Map<string, { kind?: string; title?: string }> }): ReactElement {
  return (
    <>
      <article className="message user" aria-label="用户问题">
        <div className="message-avatar">W</div>
        <div className="message-body">
          <div className="message-label">你</div>
          <div className="bubble">{turn.input.content}</div>
        </div>
      </article>
      {turn.plain_reply && (
        <article aria-label="助手回复" className="message assistant plain-reply">
          <div className="message-avatar">O</div>
          <div className="message-body">
            <div className="message-label">OperMind · 普通对话</div>
            <div className="bubble">{turn.plain_reply.content}</div>
          </div>
        </article>
      )}
      {turn.investigations.map(({ investigation, output }) => {
        const is_live = investigation.status === 'queued' || investigation.status === 'running'
        const Container = is_live || output ? 'article' : 'div'
        return (
        <Container {...(is_live || output ? { 'aria-label': '助手答复' } : {})} className="message assistant service-result" key={investigation.id}>
          <div className="message-avatar">O</div>
          <div className="service-investigation-result">
            <div className="service-result-label">{service_result_title(investigation.service_id, services_by_id)}</div>
            <AssistantReply investigation={investigation} output={output} session_id={session_id} />
          </div>
        </Container>
        )
      })}
    </>
  )
}

function ConversationTimeline({ messages, runs, services_by_id, session_id }: { messages: unknown[]; runs: unknown[]; services_by_id: Map<string, { kind?: string; title?: string }>; session_id: string }): ReactElement {
  const { issues, timeline } = useMemo(
    () => project_conversation_turns(messages, runs, session_id),
    [messages, runs, session_id],
  )

  return (
    <section className="conversation">
      {issues.map((issue, index) => (
        <UiAlert className="conversation-protocol-notice" description={issue} key={`${issue}-${index}`} showIcon title="会话关联异常" type="warning" />
      ))}
      {timeline.length === 0 && (
        <UiText className="muted-note">该会话还没有可恢复的对话内容</UiText>
      )}
      {timeline.map((item) => {
        if (item.kind === 'system') {
          return (
            <UiAlert
              className="conversation-system-message"
              description={item.message.content}
              key={item.message.id}
              showIcon
              title={`系统提醒 · ${item.message.created_at}`}
              type="info"
            />
          )
        }
        return <ConversationTurnCard key={item.turn.input.id} services_by_id={services_by_id} session_id={session_id} turn={item.turn} />
      })}
    </section>
  )
}

function SessionWorkspace({ session_id, prefilled_query }: { session_id: string; prefilled_query: string }): ReactElement {
  const navigate = useNavigate()
  const query_client = useQueryClient()
  const storage = session_storage()
  const [query, set_query] = useState(prefilled_query)
  const [send_intent, set_send_intent] = useState<SessionRunSendIntent | undefined>(() =>
    storage ? load_session_run_send_intent(storage, session_id) : undefined,
  )
  const [recovery_error, set_recovery_error] = useState<unknown>()
  const automatic_recovery_attempts = useRef(new Set<string>())
  const session_query = useQuery({ ...get_session_query(session_id), enabled: Boolean(session_id) })
  const services_query = useQuery({
    ...list_services_query(),
    enabled: Boolean(session_query.data && session_service_ids((session_query.data as ApiResponse<SessionResponse>).data.session).length > 0),
  })
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
    set_query(restored?.query ?? prefilled_query)
    set_recovery_error(undefined)
  }, [prefilled_query, session_id, storage])

  // 记录挂载时已存在的发送意图：仅对"进会话前就写好"的意图做自动提交，
  // 用户在会话内自行输入并发送的意图走手动提交，避免重复提交。
  const initial_intent_key = useRef<string | undefined>(
    storage ? load_session_run_send_intent(storage, session_id)?.runs.map((run) => run.idempotency_key).join(':') : undefined,
  )

  const reconcile_accepted_intent = async (intent: SessionRunSendIntent): Promise<void> => {
    if (!intent.runs.every((run) => run.phase === 'accepted' && run.accepted_run_id && run.input_message_id)) return
    set_recovery_error(undefined)
    const all_runs = await fetch_all_pages<DiagnosisRunListResponse>((cursor) =>
      api_v1_client.list_session_runs(session_id, { cursor, limit: API_V1_DEFAULT_PAGE_SIZE }),
    )
    const all_messages = await fetch_all_pages<MessageListResponse>((cursor) =>
      api_v1_client.list_session_messages(session_id, { cursor, limit: API_V1_DEFAULT_PAGE_SIZE }),
    )
    query_client.setQueryData(runs_query_key, all_runs)
    query_client.setQueryData(messages_query_key, all_messages)

    const recovered_run_values = all_runs.pages.flatMap((page) => read_items(page.data))
    const recovered_message_values = all_messages.pages.flatMap((page) => read_items(page.data))
    const all_accepted_found = intent.runs.every((intent_run) => recovered_run_values.some((run) => resource_optional_string(run, 'id') === intent_run.accepted_run_id
      && resource_optional_string(run, 'session_id') === session_id
      && resource_optional_string(run, 'input_message_id') === intent_run.input_message_id)
      && recovered_message_values.some((message) => resource_optional_string(message, 'id') === intent_run.input_message_id
        && resource_optional_string(message, 'session_id') === session_id
        && resource_string(message, 'role') === 'user'))
    if (!all_accepted_found) {
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
      if (!current_intent || !current_intent.runs.some((run) => run.idempotency_key === variables.idempotency_key)) {
        set_recovery_error(new Error('SEND_INTENT_MISSING：无法确认当前受理响应对应的发送意图。'))
        return
      }
      if (accepted_session_id !== session_id || !accepted_run_id || !input_message_id) {
        set_recovery_error(new Error('ACCEPT_RESPONSE_PROTOCOL_ERROR：服务端受理响应未返回当前会话的合法 Run。'))
        return
      }

      const accepted_intent = mark_session_run_send_intent_accepted(current_intent, variables.idempotency_key, accepted_run_id, input_message_id)
      if (storage) save_session_run_send_intent(storage, accepted_intent)
      set_send_intent(accepted_intent)
    },
    onError: (error) => {
      if (error instanceof ApiClientError && error.code === 'SESSION_ARCHIVED') {
        void query_client.invalidateQueries({ queryKey: api_v1_query_keys.session(session_id) })
      }
      set_recovery_error(error)
    },
  })

  useEffect(() => {
    if (!session_query.isSuccess || !send_intent?.runs.every((run) => run.phase === 'accepted') || create_run.isPending) return
    const attempt_key = `${session_id}:${send_intent.runs.map((run) => run.accepted_run_id).join(':')}`
    if (automatic_recovery_attempts.current.has(attempt_key)) return
    automatic_recovery_attempts.current.add(attempt_key)
    void reconcile_accepted_intent(send_intent).catch(set_recovery_error)
  }, [create_run.isPending, send_intent, session_id, session_query.isSuccess])

  // 从欢迎页创建的会话：挂载时就带着预写发送意图（acceptance_unknown），进入会话页后自动提交调查。
  const auto_submit_attempted = useRef<string | null>(null)
  useEffect(() => {
    if (!session_query.isSuccess || create_run.isPending) return
    if (!send_intent?.runs.some((run) => run.phase === 'acceptance_unknown')) return
    if (!send_intent.query.trim()) return
    // 仅自动提交"进会话前就写好"的意图，不处理用户在会话内新输入并发送的意图。
    if (send_intent.runs.map((run) => run.idempotency_key).join(':') !== initial_intent_key.current) return
    const attempt_key = `${session_id}:${send_intent.runs.map((run) => run.idempotency_key).join(':')}`
    if (auto_submit_attempted.current === attempt_key) return
    auto_submit_attempted.current = attempt_key
    submit_investigation(send_intent.query)
  }, [create_run.isPending, send_intent, session_id, session_query.isSuccess])

  const discard_send_intent = (): void => {
    if (storage) clear_session_run_send_intent(storage, session_id)
    set_send_intent(undefined)
    set_recovery_error(undefined)
  }

  const submit_investigation = (composer_value?: string): void => {
    if (create_run.isPending || !storage) return
    const normalized_query = (composer_value ?? query).trim()
    if (!normalized_query) {
      set_recovery_error(new Error('调查问题不能为空。'))
      return
    }

    const current_intent = send_intent ?? create_session_run_send_intent(
      session_id,
      normalized_query,
      { service_ids: session_query.data ? session_service_ids((session_query.data as ApiResponse<SessionResponse>).data.session) : [] },
    )
    if (current_intent.query !== normalized_query) {
      set_recovery_error(new Error('当前发送意图仍在恢复中；请先完成重试或明确刷新后再修改问题。'))
      return
    }
    save_session_run_send_intent(storage, current_intent)
    set_send_intent(current_intent)
    set_recovery_error(undefined)
    const submit_next = async (): Promise<void> => {
      const errors = await submit_unaccepted_session_runs(current_intent, (intent_run) =>
        create_run.mutateAsync({ idempotency_key: intent_run.idempotency_key, query: current_intent.query, service_id: intent_run.service_id, session_id }).then(() => undefined),
      )
      if (errors.length) {
        if (current_intent.runs.length === 1) {
          set_recovery_error(errors[0]!.error)
          return
        }
        const failed_services = errors.map(({ service_id }) => service_id ?? '未关联服务').join('、')
        set_recovery_error(new Error(`以下服务的调查未能提交：${failed_services}。其他服务仍会继续提交；可使用原幂等键重试未受理服务。`))
      }
    }
    void submit_next().catch(() => undefined)
  }

  const send_plain = useMutation({ ...send_plain_message_mutation() })

  /** 统一发送路由：调查意图走既有 Run 幂等链路；普通消息走独立消息通道（服务端权威 409 兜底）。 */
  const submit_text = (composer_value: string): void => {
    if (send_plain.isPending || create_run.isPending) return
    const normalized = composer_value.trim()
    if (!normalized) {
      set_recovery_error(new Error('消息内容不能为空。'))
      return
    }
    set_recovery_error(undefined)
    if (is_investigation_message(normalized)) {
      submit_investigation(normalized)
      return
    }
    send_plain.mutate(
      { session_id, content: normalized },
      {
        onSuccess: async () => {
          if (storage) clear_pending_plain_message(storage, session_id)
          set_query('')
          await Promise.all([
            query_client.invalidateQueries({ queryKey: messages_query_key }),
            query_client.invalidateQueries({ queryKey: runs_query_key }),
          ])
        },
        onError: (error) => {
          if (error instanceof ApiClientError && error.code === 'INVESTIGATION_REQUIRED') {
            submit_investigation(normalized)
            return
          }
          if (error instanceof ApiClientError && error.code === 'SESSION_ARCHIVED') {
            void query_client.invalidateQueries({ queryKey: api_v1_query_keys.session(session_id) })
          }
          set_recovery_error(error)
        },
      },
    )
  }

  // 从欢迎页创建会话时预写的普通消息：进入会话页后自动发送一次。
  const pending_plain_attempted = useRef(false)
  useEffect(() => {
    if (!session_query.isSuccess || send_plain.isPending || create_run.isPending) return
    const pending = storage ? load_pending_plain_message(storage, session_id) : undefined
    if (!pending || pending_plain_attempted.current) return
    pending_plain_attempted.current = true
    submit_text(pending.query)
  }, [create_run.isPending, send_plain.isPending, session_id, session_query.isSuccess])

  if (session_query.isPending) return <LoadingBlock label="正在恢复会话" />
  if (session_query.isError) {
    return (
      <section className="workbench-page" aria-labelledby="workbench-title">
        <UiTitle id="workbench-title" level={2}>无法恢复会话</UiTitle>
        <ApiErrorNotice error={session_query.error} />
        <UiButton className="return-workbench" onClick={() => navigate('/workbench')} type="link">返回会话列表</UiButton>
      </section>
    )
  }

  const session = (session_query.data as ApiResponse<SessionResponse>).data.session
  const session_status = resource_string(session, 'status', 'unknown')
  const selected_session_service_ids = session_service_ids(session)
  const session_service_titles = selected_session_service_ids.map((service_id) => {
    const service = read_items(services_query.data?.data).find((item) => resource_optional_string(item, 'id') === service_id)
    return resource_optional_string(service, 'title') ?? service_id
  })
  const services_by_id = new Map(read_items(services_query.data?.data).flatMap((service) => {
    const id = resource_optional_string(service, 'id')
    return id ? [[id, { kind: resource_optional_string(service, 'kind'), title: resource_optional_string(service, 'title') }] as const] : []
  }))
  const can_send = session_status === 'active'
  const has_idempotency_key_conflict = is_idempotency_key_conflict(recovery_error)
  return (
    <div className="chat-inner">
      {session_service_titles.length > 0 && (
        <div aria-label="本次调查目标服务" className="session-service-context">
          <span>调查目标服务</span>
          <strong>{session_service_titles.join('、')}</strong>
        </div>
      )}
      {session_status === 'archived' && (
        <UiAlert className="archive-notice" description="会话已归档，仅可阅读历史内容；重新激活和编辑尚未实现。" showIcon title="已归档会话" type="info" />
      )}
      {prefilled_query && !send_intent && !has_idempotency_key_conflict && (
        <UiAlert
          className="investigation-send-notice"
          description="此会话从服务中心进入，预填问题尚未提交。你可以修改问题；只有点击发送后才会创建 Message 和 Run。"
          showIcon
          title="尚未开始调查"
          type="info"
        />
      )}
      {runs_query.isPending && <LoadingBlock label="正在恢复关联调查" />}
      {runs_query.isError && <ApiErrorNotice error={runs_query.error} />}
      {runs_query.isSuccess && messages_query.isPending && <LoadingBlock label="正在恢复会话消息" />}
      {runs_query.isSuccess && messages_query.isError && <ApiErrorNotice error={messages_query.error} />}
      {runs_query.isSuccess && messages_query.isSuccess && (
        <>
          <ConversationTimeline messages={recovered_messages} runs={recovered_runs} services_by_id={services_by_id} session_id={session_id} />
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
        </>
      )}
      {can_send && (
        <Composer
          disabled={create_run.isPending || send_plain.isPending || has_idempotency_key_conflict}
          onChange={(text) => {
            set_query(text)
            if (is_validation_error(recovery_error)) set_recovery_error(undefined)
          }}
          onSubmit={submit_text}
          value={query}
        />
      )}
      {send_intent?.runs.some((run) => run.phase === 'acceptance_unknown') && (
        <UiAlert
          className="investigation-send-notice"
          description="本次请求的受理结果尚未确认。请使用同一问题和同一幂等键重试，或刷新页面恢复；不要修改问题后盲目再次发送。"
          showIcon
          title="等待确认调查是否已受理"
          type="warning"
        />
      )}
      {has_idempotency_key_conflict && (
        <UiAlert
          action={<UiButton onClick={discard_send_intent} type="link">丢弃当前发送意图</UiButton>}
          className="investigation-send-notice"
          description="幂等键已用于不同问题。请丢弃当前发送意图后重新提问。"
          showIcon
          title="发送冲突"
          type="warning"
        />
      )}
      {recovery_error !== undefined && <ApiErrorNotice error={recovery_error} />}
    </div>
  )
}

export function WorkbenchPage(): ReactElement {
  const { session_id } = useParams<{ session_id: string }>()
  const [search_params] = useSearchParams()
  const prefilled_query = search_params.get('intent') === 'orders_slow_query.v1'
    ? '订单服务变慢，帮我排查慢查询。'
    : ''
  if (session_id) return <SessionWorkspace prefilled_query={prefilled_query} session_id={session_id} />

  return <ConversationHome />
}

function ConversationHome(): ReactElement {
  const navigate = useNavigate()
  const query_client = useQueryClient()
  const storage = session_storage()
  const pending_prompt = useRef<string | null>(null)
  const [query, set_query] = useState('')
  const [selected_service_ids, set_selected_service_ids] = useState<string[]>([])
  const services_query = useQuery({ ...list_services_query() })
  const service_resources = services_query.data ? read_items(services_query.data.data) : []
  const services = service_resources.flatMap((service) => {
    const id = resource_optional_string(service, 'id')
    const title = resource_optional_string(service, 'title')
    return id && title ? [{ id, title }] : []
  })
  const service_count = service_resources.length
  const create_session = useMutation({
    ...create_session_mutation(),
    onSuccess: async (response) => {
      const created = read_record(response.data.session)
      const created_id = resource_optional_string(created, 'id')
      if (!created_id) return
      // 预写发送意图，让会话页加载后自动发送，避免"创建会话后消息丢失"。
      // 调查意图走 Run 幂等链路；普通消息走独立消息通道（不创建 Run）。
      const prompt = pending_prompt.current
      if (storage && prompt) {
        if (is_investigation_message(prompt)) {
          const intent = create_session_run_send_intent(created_id, prompt, { service_ids: selected_service_ids })
          save_session_run_send_intent(storage, intent)
        } else {
          save_pending_plain_message(storage, created_id, prompt)
        }
      }
      pending_prompt.current = null
      await query_client.invalidateQueries({ queryKey: api_v1_query_keys.sessions(default_session_list_query) })
      navigate(`/workbench/sessions/${encodeURIComponent(created_id)}`)
    },
  })
  const submit_prompt = (prompt: string): void => {
    pending_prompt.current = prompt
    create_session.mutate({ title: prompt.slice(0, 40), service_ids: selected_service_ids.length ? selected_service_ids : undefined })
  }
  return (
    <div className="chat-inner">
      <WelcomePanel
        on_prompt={submit_prompt}
        on_service_change={set_selected_service_ids}
        selected_service_ids={selected_service_ids}
        service_count={service_count}
        services={services}
      />
      <Composer
        disabled={create_session.isPending}
        onChange={set_query}
        onSubmit={submit_prompt}
        value={query}
      />
    </div>
  )
}
