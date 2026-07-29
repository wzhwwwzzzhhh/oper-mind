import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
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
import { useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import {
  API_V1_DEFAULT_PAGE_SIZE,
  ApiClientError,
  api_v1_client,
  type ApiResponse,
  type SessionResponse,
} from '../../api/v1/client'
import { api_v1_query_keys, get_session_query } from '../../api/v1/queries'
import {
  investigation_status_color,
  investigation_status_text,
  project_conversation_turns,
  type ConversationInvestigation,
  type ConversationMessage,
  type ConversationTurn,
} from './conversation-turns'
import { DiagnosisResultPanel } from './DiagnosisResultPanel'
import { read_diagnosis_result } from './result-readers'
import {
  read_items,
  read_page,
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
        会话会保存问题、调查过程和后续答复。新建会话与普通聊天发送将在后续切片提供。
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

function AssistantReply({ investigation, output }: { investigation: ConversationInvestigation; output?: ConversationMessage }): ReactElement {
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
    <Alert
      description={investigation.status === 'queued'
        ? '请求已保存，正在等待调查开始。'
        : '正在核对已保存的诊断事实；实时过程展示将在后续切片渐进加入。'}
      title={investigation.status === 'queued' ? '正在准备调查' : '正在调查'}
      showIcon
      type="info"
    />
  )
}

function InvestigationSummary({ investigation, output }: { investigation?: ConversationInvestigation; output?: ConversationMessage }): ReactElement {
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
      <AssistantReply investigation={investigation} output={output} />
    </div>
  )
}

function ConversationTurnCard({ turn }: { turn: ConversationTurn }): ReactElement {
  return (
    <article className="conversation-turn">
      <div className="conversation-message conversation-message-user" aria-label="用户问题">
        <div className="conversation-message-meta">
          <Tag color="blue">你</Tag>
          <Typography.Text type="secondary">{turn.input.created_at}</Typography.Text>
        </div>
        <Typography.Paragraph className="conversation-message-content">{turn.input.content}</Typography.Paragraph>
      </div>
      <InvestigationSummary investigation={turn.investigation} output={turn.output} />
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
          return <ConversationTurnCard key={item.turn.input.id} turn={item.turn} />
        })}
      </div>
    </Card>
  )
}

function SessionWorkspace({ session_id }: { session_id: string }): ReactElement {
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
  return (
    <section className="workbench-page" aria-labelledby="workbench-title">
      <div className="page-eyebrow">PERSONAL CONVERSATION · READ ONLY</div>
      <Space align="center" className="workbench-title-row" wrap>
        <Typography.Title id="workbench-title" level={2}>{resource_string(session, 'title', '个人会话')}</Typography.Title>
        <Tag color={status_color(session_status)}>{session_status}</Tag>
      </Space>
      <Typography.Paragraph className="page-description">
        这里按对话阅读已保存的用户问题、调查和助手答复。页面只读取 P2 v1 资源；发送、实时过程和新建会话将在后续切片提供。
      </Typography.Paragraph>
      {session_status === 'archived' && (
        <Alert className="archive-notice" description="会话已归档，仅可阅读历史内容；重新激活和编辑尚未实现。" title="已归档会话" showIcon type="info" />
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
      <div className="page-eyebrow">PERSONAL AI OPERATIONS</div>
      <Typography.Title id="workbench-title" level={2}>我的会话</Typography.Title>
      <Typography.Paragraph className="page-description">
        从已保存的个人会话恢复调查型对话。当前只读，不会伪造监控、告警、处理或普通聊天能力。
      </Typography.Paragraph>
      <SessionNavigator />
    </section>
  )
}
