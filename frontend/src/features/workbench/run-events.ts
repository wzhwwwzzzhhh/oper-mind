import { read_record, read_string } from './resource-readers'

export const RUN_EVENT_TYPES = [
  'run_queued',
  'run_started',
  'route_decided',
  'agent_start',
  'agent_done',
  'conflict_checked',
  'debate_round',
  'report',
  'reflection',
  'tool_invoked',
  'run_succeeded',
  'run_failed',
  'run_cancelled',
] as const

export type RunEventType = (typeof RUN_EVENT_TYPES)[number]

export interface PersistedRunEvent {
  data: Record<string, unknown>
  id: string
  occurred_at: string
  run_id: string
  sequence: number
  type: RunEventType
}

export function is_terminal_run_event(event: PersistedRunEvent): boolean {
  return event.type === 'run_succeeded' || event.type === 'run_failed' || event.type === 'run_cancelled'
}

export function read_persisted_run_event(value: unknown, expected_run_id: string): PersistedRunEvent | undefined {
  const record = read_record(value)
  const id = read_string(record?.id)
  const run_id = read_string(record?.run_id)
  const sequence = record?.sequence
  const type = read_string(record?.type)
  const occurred_at = read_string(record?.occurred_at)
  const data = read_record(record?.data)

  if (!id || run_id !== expected_run_id || typeof sequence !== 'number' || !Number.isSafeInteger(sequence) || sequence < 1) return undefined
  if (!type || !RUN_EVENT_TYPES.includes(type as RunEventType)) return undefined
  if (!occurred_at || Number.isNaN(Date.parse(occurred_at)) || !occurred_at.endsWith('Z')) return undefined
  if (!data) return undefined

  return {
    data,
    id,
    occurred_at,
    run_id,
    sequence,
    type: type as RunEventType,
  }
}

export function merge_persisted_run_events(
  run_id: string,
  current_events: readonly PersistedRunEvent[],
  incoming_values: readonly unknown[],
): PersistedRunEvent[] {
  const by_sequence = new Map<number, PersistedRunEvent>()
  for (const event of current_events) {
    if (event.run_id === run_id) by_sequence.set(event.sequence, event)
  }
  for (const value of incoming_values) {
    const event = read_persisted_run_event(value, run_id)
    if (event && !by_sequence.has(event.sequence)) by_sequence.set(event.sequence, event)
  }

  return [...by_sequence.values()].sort((left, right) => left.sequence - right.sequence)
}

export function read_sse_run_event(payload: string, expected_run_id: string): PersistedRunEvent | undefined {
  try {
    return read_persisted_run_event(read_record(JSON.parse(payload))?.event, expected_run_id)
  } catch {
    return undefined
  }
}

export function run_event_summary(event: PersistedRunEvent): string {
  const summary = read_string(event.data.summary)
  return summary ?? '已提交的诊断过程事件。'
}
