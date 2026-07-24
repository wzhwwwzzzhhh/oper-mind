import { afterEach, describe, expect, it, vi } from 'vitest'
import { diagnose } from './diagnosis'

const VALID_RESPONSE = {
  result: '# 运维诊断报告\n\n诊断完成',
  strategy: 'direct',
  thinking: ['route 完成'],
  trace: [
    {
      type: 'route_decided',
      node: 'route',
      detail: '兜底关键词路由 → direct',
      timestamp: '2026-07-24T00:00:00+00:00',
    },
  ],
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('diagnose', () => {
  it('以 show_thinking=true 调用同步诊断并返回契约数据', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(VALID_RESPONSE), { status: 200 }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const response = await diagnose('检查慢 SQL')

    expect(response).toEqual(VALID_RESPONSE)
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/diagnose',
      expect.objectContaining({ method: 'POST' }),
    )
    const request = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(request.body as string)).toEqual({
      query: '检查慢 SQL',
      show_thinking: true,
    })
  })

  it('将后端统一错误体转换为可展示消息', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: 'VALIDATION_ERROR', message: '请求参数不合法' }), { status: 422 }),
      ),
    )

    await expect(diagnose('')).rejects.toThrow('请求参数不合法')
  })

  it('拒绝不符合前端契约的成功响应', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ result: '报告缺少 strategy' }), { status: 200 }),
      ),
    )

    await expect(diagnose('检查服务器')).rejects.toThrow('诊断响应不符合 API 契约')
  })

  it('将 AbortSignal 透传给 fetch', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(VALID_RESPONSE), { status: 200 }),
    )
    const controller = new AbortController()
    vi.stubGlobal('fetch', fetchMock)

    await diagnose('检查服务器', controller.signal)

    const request = fetchMock.mock.calls[0][1] as RequestInit
    expect(request.signal).toBe(controller.signal)
  })

  it('非 JSON 错误响应退化为 HTTP 状态提示', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('upstream unavailable', { status: 503 })),
    )

    await expect(diagnose('检查日志')).rejects.toThrow('HTTP 503')
  })

  it('拒绝 trace 字段中的空文本', async () => {
    const invalidTrace = {
      ...VALID_RESPONSE,
      trace: [{ ...VALID_RESPONSE.trace[0], detail: '' }],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify(invalidTrace), { status: 200 })),
    )

    await expect(diagnose('检查链路')).rejects.toThrow('诊断响应不符合 API 契约')
  })
})
