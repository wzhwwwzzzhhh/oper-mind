import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { HttpResponse, http } from 'msw'

import { App } from '../../app/App'
import { api_v1_contract_fixtures } from '../../test/handlers'
import { server } from '../../test/server'

const SESSION_ID = api_v1_contract_fixtures.session_id
const MAIN_RUN_ID = '99999999-9999-4999-8999-0000000000a1'
const MAIN_INPUT_MESSAGE_ID = '99999999-9999-4999-8999-0000000000a2'
const MAIN_OUTPUT_MESSAGE_ID = '99999999-9999-4999-8999-0000000000a3'
const FAILED_RUN_ID = '99999999-9999-4999-8999-0000000000b1'
const FAILED_INPUT_MESSAGE_ID = '99999999-9999-4999-8999-0000000000b2'
const UNAVAILABLE_RUN_ID = '99999999-9999-4999-8999-0000000000c1'
const UNAVAILABLE_INPUT_MESSAGE_ID = '99999999-9999-4999-8999-0000000000c2'
const UNAVAILABLE_OUTPUT_MESSAGE_ID = '99999999-9999-4999-8999-0000000000c3'

const MATERIAL = { content_sha256: 'c'.repeat(64), material_id: 'material-a', original_text: 'alpha\nbeta' }

/** 冻结输入只由 Run 详情返回；会话摘要列表按 Design §2.8 不回显 A/B 原文。 */
const INPUT_SNAPSHOT = { query: '比较这两段文本', rule_version: 'literal-lines@1', text_a: MATERIAL, text_b: null }

const MAIN_RUN = {
  created_at: '2026-10-21T02:00:00.000Z',
  delivery: {
    a_material_id: 'material-a',
    b_material_id: 'material-b',
    blocks: [{ a_end: 2, a_quote: 'beta', a_start: 2, b_end: 2, b_quote: 'gamma', b_start: 2, kind: 'modified' }],
    capability_id: 'text.literal_compare',
    capability_version: 1,
    kind: 'comparison',
    rule_version: 'literal-lines@1',
    status: 'has_difference',
  },
  error: null,
  finished_at: '2026-10-21T02:00:03.000Z',
  id: MAIN_RUN_ID,
  input_message_id: MAIN_INPUT_MESSAGE_ID,
  input_snapshot: null,
  rerun_of_run_id: null,
  result: null,
  runtime_kind: 'main_agent',
  service_id: null,
  session_id: SESSION_ID,
  started_at: '2026-10-21T02:00:01.000Z',
  status: 'succeeded',
  trace_id: api_v1_contract_fixtures.trace_id,
}

const FAILED_RUN = {
  ...MAIN_RUN,
  created_at: '2026-10-21T03:00:00.000Z',
  delivery: null,
  error: { code: 'MAIN_AGENT_MODEL_UNAVAILABLE', message: '主 Agent 模型暂不可用，请稍后重试' },
  finished_at: '2026-10-21T03:00:02.000Z',
  id: FAILED_RUN_ID,
  input_message_id: FAILED_INPUT_MESSAGE_ID,
  result: null,
  started_at: '2026-10-21T03:00:01.000Z',
  status: 'failed',
}

/** 交付行损坏：Run 仍是 succeeded，但交付不可读，页面只能展示安全不可用。 */
const UNAVAILABLE_RUN = {
  ...MAIN_RUN,
  created_at: '2026-10-21T04:00:00.000Z',
  delivery: null,
  finished_at: '2026-10-21T04:00:03.000Z',
  id: UNAVAILABLE_RUN_ID,
  input_message_id: UNAVAILABLE_INPUT_MESSAGE_ID,
  main_delivery_status: 'unavailable',
  started_at: '2026-10-21T04:00:01.000Z',
  status: 'succeeded',
}

const MESSAGES = [
  { content: '比较这两段文本', created_at: '2026-10-21T02:00:00.000Z', id: MAIN_INPUT_MESSAGE_ID, role: 'user', run_id: null, session_id: SESSION_ID },
  { content: '文本比较完成：共 1 个差异块。', created_at: '2026-10-21T02:00:03.000Z', id: MAIN_OUTPUT_MESSAGE_ID, role: 'assistant', run_id: MAIN_RUN_ID, session_id: SESSION_ID },
  { content: '比较这两段文本', created_at: '2026-10-21T03:00:00.000Z', id: FAILED_INPUT_MESSAGE_ID, role: 'user', run_id: null, session_id: SESSION_ID },
]

function stub_conversation(runs: unknown[], messages: unknown[] = MESSAGES): void {
  server.use(
    http.get(/\/api\/v1\/sessions\/([^/]+)\/runs$/, () =>
      HttpResponse.json({
        items: runs,
        meta: { request_id: '99999999-9999-4999-8999-999999999990' },
        page: { has_more: false, next_cursor: null },
      }),
    ),
    // Run 详情按契约返回冻结输入；页面在摘要列表缺少输入时按需读取它。
    http.get(/\/api\/v1\/runs\/[0-9a-f-]+$/, ({ request }) => {
      const run_id = request.url.split('/').at(-1)
      const run = runs.find((item) => (item as { id?: string }).id === run_id) ?? runs[0]
      return HttpResponse.json({
        meta: { request_id: '99999999-9999-4999-8999-999999999994' },
        run: { ...(run as Record<string, unknown>), input_snapshot: INPUT_SNAPSHOT },
      })
    }),
    http.get(/\/api\/v1\/sessions\/([^/]+)\/messages$/, () =>
      HttpResponse.json({
        items: messages,
        meta: { request_id: '99999999-9999-4999-8999-999999999991' },
        page: { has_more: false, next_cursor: null },
      }),
    ),
    http.get(/\/api\/v1\/runs\/([^/]+)\/events$/, () =>
      HttpResponse.json({
        items: [],
        meta: { request_id: '99999999-9999-4999-8999-999999999992' },
        page: { has_more: false, next_cursor: null },
      }),
    ),
  )
}

function open_session(): void {
  window.history.replaceState({}, '', `/workbench/sessions/${SESSION_ID}`)
}

describe('会话工作台 V2 主 Agent 闭环', () => {
  beforeEach(() => window.sessionStorage.clear())

  it('切到主 Agent 入口后提交 V2 请求，时间线渲染比较交付与本次输入', async () => {
    stub_conversation([MAIN_RUN])
    let run_payload: Record<string, unknown> | undefined
    server.use(
      http.post(/\/api\/v1\/sessions\/([^/]+)\/runs$/, async ({ request }) => {
        run_payload = await request.json() as Record<string, unknown>
        return HttpResponse.json(
          { meta: { request_id: '99999999-9999-4999-8999-999999999993' }, run: { ...MAIN_RUN, status: 'queued' } },
          { status: 202 },
        )
      }),
    )
    open_session()
    const { container } = render(<App />)

    expect(await screen.findByText('存在差异')).toBeInTheDocument()
    expect(screen.getByText('文本比较完成：共 1 个差异块。')).toBeInTheDocument()
    expect(screen.getByText('A 第 2 行')).toBeInTheDocument()
    expect(screen.getByText('gamma')).toBeInTheDocument()
    expect(screen.queryByText('展开结论、证据与建议')).not.toBeInTheDocument()

    // 摘要列表不带 A/B 原文，「本次输入」由页面按需读取 Run 详情后出现。
    expect(await screen.findByText('展开本次输入')).toBeInTheDocument()
    await waitFor(() => expect(container.querySelectorAll('.main-delivery-panel__raw').length).toBeGreaterThan(1))
    const raw_nodes = container.querySelectorAll('.main-delivery-panel__raw')
    expect(raw_nodes[0]?.textContent).toBe('比较这两段文本')
    expect(raw_nodes[1]?.textContent).toBe('alpha\nbeta')
    expect(screen.getByText('未提供')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '主 Agent（V2）' }))
    expect(screen.queryByRole('textbox', { name: '调查问题' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: '主 Agent 请求' }), { target: { value: '再比较一次' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await waitFor(() => expect(run_payload).toBeDefined())
    expect(run_payload).toEqual({ query: '再比较一次', runtime_kind: 'main_agent', text_a: null, text_b: null })
  })

  it('勾选提供后即使文本为空也提交显式空串，未勾选侧仍按未提供提交', async () => {
    stub_conversation([MAIN_RUN])
    let run_payload: Record<string, unknown> | undefined
    server.use(
      http.post(/\/api\/v1\/sessions\/([^/]+)\/runs$/, async ({ request }) => {
        run_payload = await request.json() as Record<string, unknown>
        return HttpResponse.json(
          { meta: { request_id: '99999999-9999-4999-8999-999999999995' }, run: { ...MAIN_RUN, status: 'queued' } },
          { status: 202 },
        )
      }),
    )
    open_session()
    render(<App />)
    await screen.findByText('存在差异')

    fireEvent.click(screen.getByRole('button', { name: '主 Agent（V2）' }))
    fireEvent.click(screen.getByText('附加文本材料（比较两段文本时填写）'))
    // Design §2.9：提供／未提供可独立切换，勾选后空文本仍是「提供了空文本」，不塌缩成未提供。
    fireEvent.click(screen.getByRole('checkbox', { name: '提供文本 A' }))
    expect(screen.getByRole('textbox', { name: '文本 A' })).toBeEnabled()
    expect(screen.getByRole('textbox', { name: '文本 B' })).toBeDisabled()
    fireEvent.change(screen.getByRole('textbox', { name: '主 Agent 请求' }), { target: { value: '比较两段空文本' } })
    fireEvent.click(screen.getByRole('button', { name: '发送' }))

    await waitFor(() => expect(run_payload).toBeDefined())
    expect(run_payload).toEqual({ query: '比较两段空文本', runtime_kind: 'main_agent', text_a: '', text_b: null })
  })

  it('默认仍是服务调查（V1）录入，不出现主 Agent 材料录入', async () => {
    stub_conversation([MAIN_RUN])
    open_session()
    render(<App />)

    await screen.findByText('存在差异')
    expect(screen.getByRole('textbox', { name: '调查问题' })).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: '主 Agent 请求' })).not.toBeInTheDocument()
    expect(screen.queryByText('附加文本材料（比较两段文本时填写）')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '服务调查（V1）' }))
    expect(screen.getByRole('textbox', { name: '调查问题' })).toBeInTheDocument()
  })

  it('主 Agent 失败只展示安全错误，不伪造交付或诊断结论', async () => {
    stub_conversation([FAILED_RUN])
    open_session()
    render(<App />)

    expect(await screen.findByText('本次请求未完成')).toBeInTheDocument()
    expect(screen.getByText('主 Agent 模型暂不可用，请稍后重试')).toBeInTheDocument()
    expect(screen.queryByText('存在差异')).not.toBeInTheDocument()
    expect(screen.queryByText(/严重度/)).not.toBeInTheDocument()
  })

  it('交付不可用时只展示安全提示，不伪造结果也不读取原文', async () => {
    stub_conversation([UNAVAILABLE_RUN], [
      { content: '比较这两段文本', created_at: '2026-10-21T04:00:00.000Z', id: UNAVAILABLE_INPUT_MESSAGE_ID, role: 'user', run_id: null, session_id: SESSION_ID },
      { content: '主 Agent 已回复。', created_at: '2026-10-21T04:00:03.000Z', id: UNAVAILABLE_OUTPUT_MESSAGE_ID, role: 'assistant', run_id: UNAVAILABLE_RUN_ID, session_id: SESSION_ID },
    ])
    open_session()
    render(<App />)

    expect(await screen.findByText('交付不可用')).toBeInTheDocument()
    expect(screen.queryByText('存在差异')).not.toBeInTheDocument()
    expect(screen.queryByText('展开本次输入')).not.toBeInTheDocument()
  })
})
