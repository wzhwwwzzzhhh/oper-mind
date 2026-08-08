export type SendIntentPhase = 'acceptance_unknown' | 'accepted'

export interface SessionRunSendIntentRun {
  accepted_run_id?: string
  idempotency_key: string
  input_message_id?: string
  phase: SendIntentPhase
  service_id?: string
}

export interface SessionRunSendIntent {
  created_at: string
  endpoint: '/api/v1/sessions/{session_id}/runs'
  query: string
  runs: SessionRunSendIntentRun[]
  session_id: string
  version: 2
}

export interface SessionRunSubmissionError {
  error: unknown
  service_id?: string
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

function is_run(value: unknown): value is SessionRunSendIntentRun {
  if (typeof value !== 'object' || value === null) return false
  const run = value as Partial<SessionRunSendIntentRun>
  if (!is_uuid(run.idempotency_key) || (run.service_id !== undefined && typeof run.service_id !== 'string')) return false
  if (run.phase !== 'acceptance_unknown' && run.phase !== 'accepted') return false
  if (run.accepted_run_id !== undefined && !is_uuid(run.accepted_run_id)) return false
  if (run.input_message_id !== undefined && !is_uuid(run.input_message_id)) return false
  return run.phase === 'acceptance_unknown'
    ? run.accepted_run_id === undefined && run.input_message_id === undefined
    : is_uuid(run.accepted_run_id) && is_uuid(run.input_message_id)
}

function is_send_intent(value: unknown, expected_session_id: string): value is SessionRunSendIntent {
  if (typeof value !== 'object' || value === null) return false
  const intent = value as Partial<SessionRunSendIntent>
  if (intent.version !== 2 || intent.endpoint !== '/api/v1/sessions/{session_id}/runs') return false
  if (intent.session_id !== expected_session_id || !Array.isArray(intent.runs) || intent.runs.length === 0) return false
  if (typeof intent.query !== 'string' || !intent.query.trim() || !is_utc_z(intent.created_at)) return false
  return intent.runs.every(is_run)
}

function read_v1_intent(value: unknown, expected_session_id: string): SessionRunSendIntent | undefined {
  if (typeof value !== 'object' || value === null) return undefined
  const intent = value as Record<string, unknown>
  if (intent.version !== 1 || intent.session_id !== expected_session_id || !is_uuid(intent.idempotency_key)) return undefined
  if (typeof intent.query !== 'string' || !intent.query.trim() || !is_utc_z(intent.created_at)) return undefined
  const run = { accepted_run_id: intent.accepted_run_id, idempotency_key: intent.idempotency_key, input_message_id: intent.input_message_id, phase: intent.phase }
  if (!is_run(run)) return undefined
  return { created_at: intent.created_at, endpoint: '/api/v1/sessions/{session_id}/runs', query: intent.query, runs: [run], session_id: expected_session_id, version: 2 }
}

export function create_session_run_send_intent(
  session_id: string,
  query: string,
  dependencies: {
    created_at?: string
    idempotency_keys?: string[]
    service_ids?: string[]
  } = {},
): SessionRunSendIntent {
  if (!query.trim()) throw new Error('调查问题不能为空。')
  const service_ids = dependencies.service_ids ?? []
  const idempotency_keys = dependencies.idempotency_keys ?? Array.from(
    { length: Math.max(service_ids.length, 1) },
    () => globalThis.crypto.randomUUID(),
  )
  if (idempotency_keys.length !== Math.max(service_ids.length, 1) || !idempotency_keys.every(is_uuid)) throw new Error('幂等键必须是 UUID。')
  const created_at = dependencies.created_at ?? new Date().toISOString()
  if (!is_utc_z(created_at)) throw new Error('发送意图时间必须是 UTC Z。')

  return {
    created_at,
    endpoint: '/api/v1/sessions/{session_id}/runs',
    query,
    runs: (service_ids.length ? service_ids : [undefined]).map((service_id, index) => ({ idempotency_key: idempotency_keys[index]!, phase: 'acceptance_unknown', service_id })),
    session_id,
    version: 2,
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
    return is_send_intent(parsed, session_id) ? parsed : read_v1_intent(parsed, session_id)
  } catch {
    return undefined
  }
}

export function save_session_run_send_intent(storage: Storage, intent: SessionRunSendIntent): void {
  storage.setItem(storage_key(intent.session_id), JSON.stringify(intent))
}

export function mark_session_run_send_intent_accepted(
  intent: SessionRunSendIntent,
  idempotency_key: string,
  accepted_run_id: string,
  input_message_id: string,
): SessionRunSendIntent {
  if (!is_uuid(accepted_run_id) || !is_uuid(input_message_id)) {
    throw new Error('受理响应缺少合法的 Run 或输入消息标识。')
  }

  return {
    ...intent,
    runs: intent.runs.map((run) => run.idempotency_key === idempotency_key
      ? { ...run, accepted_run_id, input_message_id, phase: 'accepted' }
      : run),
  }
}

/** Submit every unaccepted service run in order, retaining accepted runs for recovery. */
export async function submit_unaccepted_session_runs(
  intent: SessionRunSendIntent,
  submit: (run: SessionRunSendIntentRun) => Promise<void>,
): Promise<SessionRunSubmissionError[]> {
  const errors: SessionRunSubmissionError[] = []
  for (const run of intent.runs) {
    if (run.phase === 'accepted') continue
    try {
      await submit(run)
    } catch (error) {
      errors.push({ error, service_id: run.service_id })
    }
  }
  return errors
}

export function clear_session_run_send_intent(storage: Storage, session_id: string): void {
  storage.removeItem(storage_key(session_id))
}
