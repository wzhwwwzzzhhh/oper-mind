export type SendIntentPhase = 'acceptance_unknown' | 'accepted'

export interface SessionRunSendIntent {
  accepted_run_id?: string
  created_at: string
  endpoint: '/api/v1/sessions/{session_id}/runs'
  idempotency_key: string
  input_message_id?: string
  phase: SendIntentPhase
  query: string
  session_id: string
  version: 1
}

const STORAGE_PREFIX = 'opermind:p3.6b:send-intent:'

function storage_key(session_id: string): string {
  return `${STORAGE_PREFIX}${session_id}`
}

function is_uuid(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
}

function is_utc_z(value: unknown): value is string {
  return typeof value === 'string' && value.endsWith('Z') && !Number.isNaN(Date.parse(value))
}

function is_send_intent(value: unknown, expected_session_id: string): value is SessionRunSendIntent {
  if (typeof value !== 'object' || value === null) return false
  const intent = value as Partial<SessionRunSendIntent>
  if (intent.version !== 1 || intent.endpoint !== '/api/v1/sessions/{session_id}/runs') return false
  if (intent.session_id !== expected_session_id || !is_uuid(intent.idempotency_key)) return false
  if (typeof intent.query !== 'string' || !intent.query.trim() || !is_utc_z(intent.created_at)) return false
  if (intent.phase !== 'acceptance_unknown' && intent.phase !== 'accepted') return false
  if (intent.accepted_run_id !== undefined && !is_uuid(intent.accepted_run_id)) return false
  if (intent.input_message_id !== undefined && !is_uuid(intent.input_message_id)) return false
  return intent.phase === 'acceptance_unknown'
    ? intent.accepted_run_id === undefined && intent.input_message_id === undefined
    : is_uuid(intent.accepted_run_id) && is_uuid(intent.input_message_id)
}

export function create_session_run_send_intent(
  session_id: string,
  query: string,
  dependencies: {
    created_at?: string
    idempotency_key?: string
  } = {},
): SessionRunSendIntent {
  if (!query.trim()) throw new Error('调查问题不能为空。')
  const idempotency_key = dependencies.idempotency_key ?? globalThis.crypto.randomUUID()
  if (!is_uuid(idempotency_key)) throw new Error('幂等键必须是 UUID。')
  const created_at = dependencies.created_at ?? new Date().toISOString()
  if (!is_utc_z(created_at)) throw new Error('发送意图时间必须是 UTC Z。')

  return {
    created_at,
    endpoint: '/api/v1/sessions/{session_id}/runs',
    idempotency_key,
    phase: 'acceptance_unknown',
    query,
    session_id,
    version: 1,
  }
}

export function load_session_run_send_intent(
  storage: Storage,
  session_id: string,
): SessionRunSendIntent | undefined {
  const serialized = storage.getItem(storage_key(session_id))
  if (!serialized) return undefined

  try {
    const parsed: unknown = JSON.parse(serialized)
    return is_send_intent(parsed, session_id) ? parsed : undefined
  } catch {
    return undefined
  }
}

export function save_session_run_send_intent(storage: Storage, intent: SessionRunSendIntent): void {
  storage.setItem(storage_key(intent.session_id), JSON.stringify(intent))
}

export function mark_session_run_send_intent_accepted(
  intent: SessionRunSendIntent,
  accepted_run_id: string,
  input_message_id: string,
): SessionRunSendIntent {
  if (!is_uuid(accepted_run_id) || !is_uuid(input_message_id)) {
    throw new Error('受理响应缺少合法的 Run 或输入消息标识。')
  }

  return {
    ...intent,
    accepted_run_id,
    input_message_id,
    phase: 'accepted',
  }
}

export function clear_session_run_send_intent(storage: Storage, session_id: string): void {
  storage.removeItem(storage_key(session_id))
}
