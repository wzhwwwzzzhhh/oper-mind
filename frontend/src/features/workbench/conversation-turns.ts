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
  status: InvestigationStatus
  trace_id?: string
}

export interface ConversationTurn {
  input: ConversationMessage
  investigation?: ConversationInvestigation
  output?: ConversationMessage
}

export type ConversationTimelineItem =
  | { kind: 'system'; message: ConversationMessage }
  | { kind: 'turn'; turn: ConversationTurn }

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
  const duplicated_input_message_ids = new Set<string>()
  const output_by_run_id = new Map<string, ConversationMessage>()

  for (const investigation of investigations) {
    if (!message_by_id.has(investigation.input_message_id)) {
      issues.push(`RUN_INPUT_MESSAGE_MISSING：调查 ${investigation.id} 未找到对应的用户消息。`)
      continue
    }
    if (investigation_by_input_id.has(investigation.input_message_id)) {
      investigation_by_input_id.delete(investigation.input_message_id)
      duplicated_input_message_ids.add(investigation.input_message_id)
      issues.push(`RUN_INPUT_MESSAGE_DUPLICATED：一条用户消息关联了多个调查，当前只读视图不会自行选择。`)
      continue
    }
    if (!duplicated_input_message_ids.has(investigation.input_message_id)) {
      investigation_by_input_id.set(investigation.input_message_id, investigation)
    }
  }

  for (const message of messages) {
    if (message.role !== 'assistant') continue
    if (!message.run_id) {
      issues.push(`ASSISTANT_MESSAGE_RUN_MISSING：助手消息 ${message.id} 未关联调查。`)
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
  for (const message of messages) {
    if (message.role === 'system') {
      timeline.push({ kind: 'system', message })
      continue
    }
    if (message.role !== 'user') continue

    const investigation = investigation_by_input_id.get(message.id)
    timeline.push({
      kind: 'turn',
      turn: {
        input: message,
        investigation,
        output: investigation ? output_by_run_id.get(investigation.id) : undefined,
      },
    })
  }

  return { issues, timeline }
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
