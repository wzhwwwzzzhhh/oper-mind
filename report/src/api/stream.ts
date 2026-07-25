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

export interface StreamCompleteEvent extends DiagnoseResponse {
  type: 'complete'
  trace: TraceEvent[]
}

export interface StreamErrorEvent {
  type: 'error'
  code: string
  message: string
}

export interface DiagnosisStreamHandlers {
  onProgress: (event: TraceEvent) => void
  onComplete: (event: StreamCompleteEvent) => void
  onError: (error: Error) => void
}

export interface EventSourceLike {
  addEventListener: (type: string, listener: (event: MessageEvent) => void) => void
  close: () => void
}

export type EventSourceFactory = (url: string) => EventSourceLike

function hasText(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0
}

export function isTraceEvent(value: unknown): value is TraceEvent {
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

function isStreamCompleteEvent(value: unknown): value is StreamCompleteEvent {
  if (typeof value !== 'object' || value === null) return false
  const event = value as Record<string, unknown>
  return (
    event.type === 'complete'
    && typeof event.result === 'string'
    && typeof event.strategy === 'string'
    && Array.isArray(event.trace)
    && event.trace.every(isTraceEvent)
  )
}

function isStreamErrorEvent(value: unknown): value is StreamErrorEvent {
  if (typeof value !== 'object' || value === null) return false
  const event = value as Record<string, unknown>
  return event.type === 'error' && hasText(event.code) && hasText(event.message)
}

function parsePayload(event: MessageEvent): unknown {
  if (typeof event.data !== 'string') throw new Error('SSE 事件数据格式错误')
  try {
    return JSON.parse(event.data) as unknown
  } catch {
    throw new Error('SSE 事件不是有效 JSON')
  }
}

function defaultEventSourceFactory(url: string): EventSourceLike {
  return new EventSource(url)
}

/** 订阅 M6 命名 SSE 事件；任何终态都会关闭连接，调用方可安全调用返回的取消函数。 */
export function subscribeDiagnosisStream(
  query: string,
  handlers: DiagnosisStreamHandlers,
  createEventSource: EventSourceFactory = defaultEventSourceFactory,
): () => void {
  const url = `${API_PREFIX}/diagnose/stream?query=${encodeURIComponent(query)}`
  let source: EventSourceLike
  try {
    source = createEventSource(url)
  } catch (error) {
    handlers.onError(error instanceof Error ? error : new Error('无法创建 SSE 连接'))
    return () => {}
  }
  let closed = false

  function close(): void {
    if (closed) return
    closed = true
    source.close()
  }

  function fail(error: Error): void {
    if (closed) return
    close()
    handlers.onError(error)
  }

  source.addEventListener('progress', (event) => {
    if (closed) return
    try {
      const payload = parsePayload(event)
      if (!isTraceEvent(payload)) throw new Error('SSE progress 事件不符合 API 契约')
      handlers.onProgress(payload)
    } catch (error) {
      fail(error instanceof Error ? error : new Error('SSE progress 事件处理失败'))
    }
  })

  source.addEventListener('complete', (event) => {
    if (closed) return
    try {
      const payload = parsePayload(event)
      if (!isStreamCompleteEvent(payload)) throw new Error('SSE complete 事件不符合 API 契约')
      close()
      handlers.onComplete(payload)
    } catch (error) {
      fail(error instanceof Error ? error : new Error('SSE complete 事件处理失败'))
    }
  })

  source.addEventListener('error', (event) => {
    if (closed) return
    try {
      const payload = parsePayload(event)
      if (!isStreamErrorEvent(payload)) throw new Error('SSE error 事件不符合 API 契约')
      fail(new Error(payload.message))
    } catch (error) {
      fail(error instanceof Error ? error : new Error('SSE 连接中断'))
    }
  })

  return close
}
