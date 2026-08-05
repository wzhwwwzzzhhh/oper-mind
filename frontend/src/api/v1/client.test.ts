import { HttpResponse, http } from 'msw'
import { describe, expect, it } from 'vitest'

import { api_v1_client, create_api_v1_client } from './client'
import { api_v1_contract_fixtures } from '../../test/handlers'
import { server } from '../../test/server'

describe('v1 API 客户端', () => {
  it('传递原样 cursor、Accept 与 X-Request-Id，并读取关联信息', async () => {
    const client = create_api_v1_client({ request_id_factory: () => 'client-request-id' })
    server.use(
      http.get('http://localhost/api/v1/sessions', ({ request }) => {
        const url = new URL(request.url)
        expect(url.searchParams.get('cursor')).toBe('opaque+/cursor==')
        expect(request.headers.get('Accept')).toBe('application/json')
        expect(request.headers.get('X-Request-Id')).toBe('client-request-id')
        return HttpResponse.json(
          {
            items: [],
            page: { next_cursor: null, has_more: false },
            meta: { request_id: 'client-request-id', trace_id: 'server-trace-id' },
          },
          {
            headers: {
              'Content-Type': 'application/json',
              'X-Request-Id': 'client-request-id',
              'X-Trace-Id': 'server-trace-id',
            },
          },
        )
      }),
    )

    const result = await client.list_sessions({
      cursor: 'opaque+/cursor==',
      limit: 20,
      status: 'active',
    })

    expect(result.data.items).toHaveLength(0)
    expect(result.diagnostics).toMatchObject({
      request_id: 'client-request-id',
      response_request_id: 'client-request-id',
      response_trace_id: 'server-trace-id',
      status: 200,
      protocol_issues: [],
    })
  })

  it('默认客户端在请求时读取当前 fetch，供页面 MSW 契约测试使用', async () => {
    const result = await api_v1_client.list_sessions()

    expect(result.data.items).toHaveLength(1)
    expect(result.diagnostics.status).toBe(200)
  })
  it('读取受控的 SESSION_NOT_FOUND 错误而不伪造成内部错误', async () => {
    const client = create_api_v1_client({ request_id_factory: () => 'missing-session-request-id' })

    await expect(client.get_session('not-found')).rejects.toMatchObject({
      name: 'ApiClientError',
      code: 'SESSION_NOT_FOUND',
      message: '会话不存在',
      diagnostics: {
        status: 404,
        response_trace_id: api_v1_contract_fixtures.trace_id,
      },
    })
  })

  it('按 opaque cursor 读取 RunEvent，并保留请求关联诊断', async () => {
    const client = create_api_v1_client({ request_id_factory: () => 'event-request-id' })

    const result = await client.list_run_events(api_v1_contract_fixtures.run_id, {
      cursor: 'run-event-page-2',
      limit: 20,
    })

    expect(result.data.items).toEqual([api_v1_contract_fixtures.run_events[1]])
    expect(result.diagnostics).toMatchObject({
      request_id: 'event-request-id',
      response_trace_id: api_v1_contract_fixtures.trace_id,
      status: 200,
    })
  })

  it('保留 run 的 session_id，供后续 UI 阶段做跨会话保护', async () => {
    const client = create_api_v1_client()
    const result = await client.get_run(api_v1_contract_fixtures.run_id)

    expect(result.data.run).toMatchObject({
      id: api_v1_contract_fixtures.run_id,
      session_id: api_v1_contract_fixtures.session_id,
      status: 'succeeded',
    })
  })

  it('以 POST JSON、幂等键和独立请求 ID 受理 Run', async () => {
    const requests: Request[] = []
    const client = create_api_v1_client({
      fetch_impl: async (input, init) => {
        requests.push(new Request(input, init))
        return HttpResponse.json(
          { run: { id: 'accepted-run', session_id: 'session-1' }, meta: { request_id: 'post-request-id' } },
          {
            status: 202,
            headers: {
              'Content-Type': 'application/json',
              'X-Request-Id': 'post-request-id',
              'X-Trace-Id': 'post-trace-id',
            },
          },
        )
      },
      request_id_factory: () => 'post-request-id',
    })

    const result = await client.create_run(
      'session-1',
      { query: '请检查 Nginx 5xx。' },
      { idempotency_key: '55555555-5555-4555-8555-555555555555' },
    )

    expect(requests).toHaveLength(1)
    expect(requests[0]?.method).toBe('POST')
    expect(requests[0]?.headers.get('Content-Type')).toBe('application/json')
    expect(requests[0]?.headers.get('Idempotency-Key')).toBe('55555555-5555-4555-8555-555555555555')
    expect(requests[0]?.headers.get('X-Request-Id')).toBe('post-request-id')
    await expect(requests[0]?.json()).resolves.toEqual({ query: '请检查 Nginx 5xx。' })
    expect(result.diagnostics).toMatchObject({ status: 202, request_id: 'post-request-id' })
  })

  it('创建普通会话时携带选定的 service_id', async () => {
    const requests: Request[] = []
    const client = create_api_v1_client({
      fetch_impl: async (input, init) => {
        requests.push(new Request(input, init))
        return HttpResponse.json(
          { session: { id: 'session-1', service_id: 'postgres-staging' }, meta: { request_id: 'session-request-id' } },
          { status: 201, headers: { 'Content-Type': 'application/json', 'X-Request-Id': 'session-request-id' } },
        )
      },
      request_id_factory: () => 'session-request-id',
    })

    await client.create_session({ title: '预发布调查', service_id: 'postgres-staging' })

    expect(requests).toHaveLength(1)
    await expect(requests[0]?.json()).resolves.toEqual({ title: '预发布调查', service_id: 'postgres-staging' })
  })

  it('将网络中断明确标记为 transport 错误', async () => {
    const client = create_api_v1_client({
      fetch_impl: async () => Promise.reject(new TypeError('network unavailable')),
      request_id_factory: () => 'network-request-id',
    })

    await expect(client.list_sessions()).rejects.toEqual(
      expect.objectContaining({
        code: 'NETWORK_ERROR',
        diagnostics: expect.objectContaining({ request_id: 'network-request-id', status: 0 }),
      }),
    )
  })

  it('将取消明确标记为 abort，而不标记为 Run 失败', async () => {
    const controller = new AbortController()
    controller.abort()
    const client = create_api_v1_client({
      fetch_impl: async () => Promise.reject(new DOMException('aborted', 'AbortError')),
      request_id_factory: () => 'abort-request-id',
    })

    await expect(client.list_sessions({}, { signal: controller.signal })).rejects.toEqual(
      expect.objectContaining({
        code: 'REQUEST_ABORTED',
        diagnostics: expect.objectContaining({ request_id: 'abort-request-id', status: 0 }),
      }),
    )
  })

  it('将非 JSON 成功响应标记为协议错误', async () => {
    const client = create_api_v1_client({
      fetch_impl: async () => new Response('<html>gateway</html>', { status: 200 }),
      request_id_factory: () => 'protocol-request-id',
    })

    await expect(client.list_sessions()).rejects.toEqual(
      expect.objectContaining({
        code: 'INVALID_API_RESPONSE',
        diagnostics: expect.objectContaining({ request_id: 'protocol-request-id', status: 200 }),
      }),
    )
  })

  it('记录 header 与 meta 的关联 ID 不一致，而不把它写入资源状态', async () => {
    const client = create_api_v1_client({
      fetch_impl: async () =>
        HttpResponse.json(
          { items: [], page: { next_cursor: null, has_more: false }, meta: { request_id: 'meta-id' } },
          {
            headers: {
              'Content-Type': 'application/json',
              'X-Request-Id': 'header-id',
              'X-Trace-Id': 'header-trace-id',
            },
          },
        ),
      request_id_factory: () => 'client-id',
    })

    const result = await client.list_sessions()
    expect(result.diagnostics.protocol_issues).toEqual([
      'request_id_mismatch',
      'request_id_header_meta_mismatch',
    ])
  })

  it('读取服务快照、活动并以无 body POST 创建服务上下文会话', async () => {
    const requests: Request[] = []
    const client = create_api_v1_client({
      fetch_impl: async (input, init) => {
        const request = new Request(input, init)
        requests.push(request)
        const path = new URL(request.url).pathname
        const body = path.endsWith('/sessions')
          ? { session: api_v1_contract_fixtures.service_session, meta: { request_id: 'service-request-id' } }
          : path.endsWith('/activities')
            ? { items: [api_v1_contract_fixtures.service_activity], page: { next_cursor: null, has_more: false }, meta: { request_id: 'service-request-id' } }
            : { service: api_v1_contract_fixtures.order_service, meta: { request_id: 'service-request-id' } }
        return HttpResponse.json(body, {
          status: path.endsWith('/sessions') ? 201 : 200,
          headers: { 'Content-Type': 'application/json', 'X-Request-Id': 'service-request-id' },
        })
      },
      request_id_factory: () => 'service-request-id',
    })

    const service = await client.get_service('order-service')
    const activities = await client.list_service_activities('order-service', { limit: 20 })
    const created = await client.create_service_session('order-service')

    expect((service.data.service as { id?: unknown }).id).toBe('order-service')
    expect(activities.data.items).toHaveLength(1)
    expect((created.data.session as { service_id?: unknown }).service_id).toBe('order-service')
    expect(requests.map((request) => request.method)).toEqual(['GET', 'GET', 'POST'])
    expect(requests[2]?.headers.get('Content-Type')).toBeNull()
  })

})
