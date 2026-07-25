import type { DiagnoseResponse, TraceEvent } from '../types/api'

const API_PREFIX = '/api'
const TRACE_TYPES = new Set([
  'route_decided',
  'agent_start',
  'agent_done',
  'conflict_checked',
  'debate_round',
  'report',
  'reflection',
])

function hasText(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

function isTraceEvent(value: unknown): value is TraceEvent {
  if (typeof value !== 'object' || value === null) return false
  const event = value as Record<string, unknown>
  return (
    hasText(event.type)
    && TRACE_TYPES.has(event.type)
    && hasText(event.node)
    && hasText(event.detail)
    && hasText(event.timestamp)
  )
}

function isDiagnoseResponse(value: unknown): value is DiagnoseResponse {
  if (typeof value !== 'object' || value === null) return false
  const payload = value as Record<string, unknown>
  const thinkingIsValid = payload.thinking === null || payload.thinking === undefined
    || (Array.isArray(payload.thinking) && payload.thinking.every((item) => typeof item === 'string'))
  const traceIsValid = payload.trace === null || payload.trace === undefined
    || (Array.isArray(payload.trace) && payload.trace.every(isTraceEvent))
  return (
    typeof payload.result === 'string'
    && typeof payload.strategy === 'string'
    && thinkingIsValid
    && traceIsValid
  )
}

async function readError(response: Response): Promise<Error> {
  try {
    const body = (await response.json()) as { message?: string; code?: string }
    return new Error(body.message || body.code || `请求失败（HTTP ${response.status}）`)
  } catch {
    return new Error(`请求失败（HTTP ${response.status}）`)
  }
}

export async function diagnose(
  query: string,
  signal?: AbortSignal,
): Promise<DiagnoseResponse> {
  const response = await fetch(`${API_PREFIX}/diagnose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, show_thinking: true }),
    signal,
  })
  if (!response.ok) {
    throw await readError(response)
  }

  const payload: unknown = await response.json()
  if (!isDiagnoseResponse(payload)) {
    throw new Error('诊断响应不符合 API 契约')
  }
  return payload
}
