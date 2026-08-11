import {
  read_record,
  resource_optional_string,
  resource_value,
} from './resource-readers'

export type ConversationMessageRole = 'assistant' | 'system' | 'user'
export type InvestigationStatus = 'cancelled' | 'failed' | 'queued' | 'running' | 'succeeded'

export interface ConversationMessage {
  content: string
  created_at: string
  id: string
  role: ConversationMessageRole
  run_id?: string
}

export interface ConversationInvestigation {
  error: unknown
  id: string
  input_message_id: string
  result: unknown
  service_id?: string
  status: InvestigationStatus
  trace_id?: string
}

export interface ConversationTurn {
  input: ConversationMessage
  investigations: Array<{ investigation: ConversationInvestigation; output?: ConversationMessage }>
  /** 普通对话回复（无 Run 关联的 assistant 消息），仅普通消息通道产生。 */
  plain_reply?: ConversationMessage
}

export type ConversationTimelineItem =
  | { kind: 'system'; message: ConversationMessage }
  | { kind: 'turn'; turn: ConversationTurn }
  | { kind: 'plain_reply'; message: ConversationMessage }

export interface ConversationProjection {
  issues: string[]
  timeline: ConversationTimelineItem[]
}

const MESSAGE_ROLES: ReadonlySet<string> = new Set(['assistant', 'system', 'user'])
const INVESTIGATION_STATUSES: ReadonlySet<string> = new Set(['cancelled', 'failed', 'queued', 'running', 'succeeded'])

function read_message(value: unknown, session_id: string, issues: string[]): ConversationMessage | undefined {
  const id = resource_optional_string(value, 'id')
  const resource_session_id = resource_optional_string(value, 'session_id')
  const role = resource_optional_string(value, 'role')
  const content = resource_optional_string(value, 'content')
  const created_at = resource_optional_string(value, 'created_at')
  const run_id = resource_optional_string(value, 'run_id')

  if (!id || !resource_session_id || !role || !content || !created_at) {
    issues.push('MESSAGE_PROTOCOL_ERROR：服务端返回的消息缺少展示所需字段。')
    return undefined
  }
  if (resource_session_id !== session_id) {
    issues.push(`MESSAGE_SESSION_MISMATCH：消息 ${id} 不属于当前会话。`)
    return undefined
  }
  if (!MESSAGE_ROLES.has(role)) {
    issues.push(`MESSAGE_ROLE_ERROR：消息 ${id} 的角色不受支持。`)
    return undefined
  }

  return {
    content,
    created_at,
    id,
    role: role as ConversationMessageRole,
    run_id,
  }
}

function read_investigation(value: unknown, session_id: string, issues: string[]): ConversationInvestigation | undefined {
  const id = resource_optional_string(value, 'id')
  const resource_session_id = resource_optional_string(value, 'session_id')
  const input_message_id = resource_optional_string(value, 'input_message_id')
  const status = resource_optional_string(value, 'status')
  const trace_id = resource_optional_string(value, 'trace_id')
  const service_id = resource_optional_string(value, 'service_id')
  const record = read_record(value)

  if (!id || !resource_session_id || !input_message_id || !status || !record) {
    issues.push('RUN_PROTOCOL_ERROR：服务端返回的调查缺少展示所需字段。')
    return undefined
  }
  if (resource_session_id !== session_id) {
    issues.push(`RUN_SESSION_MISMATCH：调查 ${id} 不属于当前会话。`)
    return undefined
  }
  if (!INVESTIGATION_STATUSES.has(status)) {
    issues.push(`RUN_STATUS_ERROR：调查 ${id} 的状态不受支持。`)
    return undefined
  }
  if (!Object.hasOwn(record, 'result') || !Object.hasOwn(record, 'error')) {
    issues.push(`RUN_PROTOCOL_ERROR：调查 ${id} 缺少结果或安全错误字段。`)
    return undefined
  }

  return {
    error: resource_value(value, 'error'),
    id,
    input_message_id,
    result: resource_value(value, 'result'),
    service_id,
    status: status as InvestigationStatus,
    trace_id,
  }
}

/**
 * 将 P2 的 Message 与 DiagnosisRun 投影为会话主线的 Turn。
 * 该投影不创建、修复或猜测服务端资源；关联不一致时只返回协议问题。
 */
export function project_conversation_turns(
  message_values: unknown[],
  run_values: unknown[],
  session_id: string,
): ConversationProjection {
  const issues: string[] = []
  const messages = message_values
    .map((value) => read_message(value, session_id, issues))
    .filter((message): message is ConversationMessage => message !== undefined)
  const investigations = run_values
    .map((value) => read_investigation(value, session_id, issues))
    .filter((investigation): investigation is ConversationInvestigation => investigation !== undefined)
  const message_by_id = new Map(messages.map((message) => [message.id, message]))
  const investigation_by_input_id = new Map<string, ConversationInvestigation>()
  const output_by_run_id = new Map<string, ConversationMessage>()
  const plain_replies: ConversationMessage[] = []

  for (const investigation of investigations) {
    if (!message_by_id.has(investigation.input_message_id)) {
      issues.push(`RUN_INPUT_MESSAGE_MISSING：调查 ${investigation.id} 未找到对应的用户消息。`)
      continue
    }
    if (investigation_by_input_id.has(investigation.input_message_id)) {
      issues.push(`RUN_INPUT_MESSAGE_DUPLICATED：一条用户消息关联了多个调查，当前只读视图不会自行选择。`)
      continue
    }
    investigation_by_input_id.set(investigation.input_message_id, investigation)
  }

  for (const message of messages) {
    if (message.role !== 'assistant') continue
    if (!message.run_id) {
      // P8 独立消息通道：无 Run 关联的 assistant 消息是普通对话回复，不再视为协议异常。
      plain_replies.push(message)
      continue
    }
    if (!investigations.some((investigation) => investigation.id === message.run_id)) {
      issues.push(`ASSISTANT_MESSAGE_RUN_MISSING：助手消息 ${message.id} 关联的调查不存在。`)
      continue
    }
    if (output_by_run_id.has(message.run_id)) {
      issues.push(`ASSISTANT_MESSAGE_DUPLICATED：调查 ${message.run_id} 关联了多条助手消息。`)
      continue
    }
    output_by_run_id.set(message.run_id, message)
  }

  const timeline: ConversationTimelineItem[] = []
  let next_plain_reply = 0
  for (const message of messages) {
    if (message.role === 'system') {
      timeline.push({ kind: 'system', message })
      continue
    }
    if (message.role !== 'user') continue

    const investigation = investigation_by_input_id.get(message.id)
    if (investigation) {
      timeline.push({
        kind: 'turn',
        turn: {
          input: message,
          investigations: [{ investigation, output: output_by_run_id.get(investigation.id) }],
        },
      })
      continue
    }
    // 普通消息：按出现顺序就近配对后续的普通回复（后端保证回复严格晚于其 user 消息）。
    const plain_reply = plain_replies[next_plain_reply]
    if (plain_reply) next_plain_reply += 1
    timeline.push({
      kind: 'turn',
      turn: {
        input: message,
        investigations: [],
        plain_reply,
      },
    })
  }

  // 无前驱 user 消息的普通回复（如分页边界）作为独立回复展示，不静默丢弃。
  for (let index = next_plain_reply; index < plain_replies.length; index += 1) {
    timeline.push({ kind: 'plain_reply', message: plain_replies[index]! })
  }

  // Each Run persists its own user message. Only adjacent equal questions form one multi-service turn.
  const grouped_timeline: ConversationTimelineItem[] = []
  for (const item of timeline) {
    if (item.kind !== 'turn') {
      grouped_timeline.push(item)
      continue
    }
    const previous = grouped_timeline.at(-1)
    const previous_turn = previous?.kind === 'turn' ? previous.turn : undefined
    const previous_service_ids = new Set(previous_turn?.investigations.flatMap(({ investigation }) =>
      investigation.service_id ? [investigation.service_id] : [],
    ))
    const service_id = item.turn.investigations[0]?.investigation.service_id
    const adjacent = previous_turn
      && previous_turn.input.content === item.turn.input.content
      && Math.abs(Date.parse(item.turn.input.created_at) - Date.parse(previous_turn.input.created_at)) <= 10_000
      && service_id !== undefined
      && !previous_service_ids.has(service_id)
    if (adjacent) {
      previous_turn.investigations.push(...item.turn.investigations)
    } else {
      grouped_timeline.push(item)
    }
  }

  return { issues, timeline: grouped_timeline }
}

export function investigation_status_text(status: InvestigationStatus): string {
  return {
    cancelled: '调查已取消',
    failed: '调查未完成',
    queued: '正在准备调查',
    running: '正在调查',
    succeeded: '调查已完成',
  }[status]
}

export function investigation_status_color(status: InvestigationStatus): string {
  return {
    cancelled: 'default',
    failed: 'red',
    queued: 'gold',
    running: 'blue',
    succeeded: 'green',
  }[status]
}
