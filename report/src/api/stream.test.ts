import { afterEach, describe, expect, it, vi } from 'vitest'
import { subscribeDiagnosisStream, type EventSourceFactory, type EventSourceLike } from './stream'

const TRACE_EVENT = {
  type: 'route_decided',
  node: 'route',
  detail: '兜底关键词路由 → direct',
  timestamp: '2026-07-24T00:00:00+00:00',
}

class FakeEventSource implements EventSourceLike {
  readonly listeners = new Map<string, (event: MessageEvent) => void>()
  readonly close = vi.fn()

  addEventListener(type: string, listener: (event: MessageEvent) => void): void {
    this.listeners.set(type, listener)
  }

  emit(type: string, payload?: unknown): void {
    this.listeners.get(type)?.({ data: payload === undefined ? undefined : JSON.stringify(payload) } as MessageEvent)
  }
}

function createFactory(): { factory: EventSourceFactory; source: FakeEventSource } {
  const source = new FakeEventSource()
  return { factory: vi.fn(() => source), source }
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('subscribeDiagnosisStream', () => {
  it('编码 query，并将 progress 交给调用方', () => {
    const { factory, source } = createFactory()
    const onProgress = vi.fn()
    subscribeDiagnosisStream('慢 SQL & 超时', { onProgress, onComplete: vi.fn(), onError: vi.fn() }, factory)

    expect(factory).toHaveBeenCalledWith('/api/diagnose/stream?query=%E6%85%A2%20SQL%20%26%20%E8%B6%85%E6%97%B6')
    source.emit('progress', TRACE_EVENT)
    expect(onProgress).toHaveBeenCalledWith(TRACE_EVENT)
    expect(source.close).not.toHaveBeenCalled()
  })

  it('complete 校验通过后关闭连接并交付最终报告', () => {
    const { factory, source } = createFactory()
    const onComplete = vi.fn()
    subscribeDiagnosisStream('检查系统', { onProgress: vi.fn(), onComplete, onError: vi.fn() }, factory)
    const complete = { type: 'complete', result: '诊断完成', strategy: 'direct', trace: [TRACE_EVENT] }

    source.emit('complete', complete)

    expect(onComplete).toHaveBeenCalledWith(complete)
    expect(source.close).toHaveBeenCalledTimes(1)
  })

  it('服务 error、断流或不合法事件都会关闭连接并报告错误', () => {
    const { factory, source } = createFactory()
    const onError = vi.fn()
    subscribeDiagnosisStream('检查系统', { onProgress: vi.fn(), onComplete: vi.fn(), onError }, factory)

    source.emit('error', { type: 'error', code: 'STREAM_FAILED', message: '流式诊断失败' })

    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: '流式诊断失败' }))
    expect(source.close).toHaveBeenCalledTimes(1)
  })

  it('浏览器断流且没有 payload 时关闭连接并报告错误', () => {
    const { factory, source } = createFactory()
    const onError = vi.fn()
    subscribeDiagnosisStream('检查系统', { onProgress: vi.fn(), onComplete: vi.fn(), onError }, factory)

    source.emit('error')

    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: 'SSE 事件数据格式错误' }))
    expect(source.close).toHaveBeenCalledTimes(1)
  })
  it('创建 EventSource 失败时立即报告错误，供调用方降级', () => {
    const onError = vi.fn()
    const factory: EventSourceFactory = () => {
      throw new Error('浏览器不支持 SSE')
    }

    const cancel = subscribeDiagnosisStream('检查系统', { onProgress: vi.fn(), onComplete: vi.fn(), onError }, factory)

    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: '浏览器不支持 SSE' }))
    expect(() => cancel()).not.toThrow()
  })
  it('取消订阅后忽略迟到事件，且关闭操作幂等', () => {
    const { factory, source } = createFactory()
    const onProgress = vi.fn()
    const cancel = subscribeDiagnosisStream('检查系统', { onProgress, onComplete: vi.fn(), onError: vi.fn() }, factory)

    cancel()
    cancel()
    source.emit('progress', TRACE_EVENT)

    expect(source.close).toHaveBeenCalledTimes(1)
    expect(onProgress).not.toHaveBeenCalled()
  })
})
