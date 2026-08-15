import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { HttpResponse, http } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { server } from '../../test/server'
import { WorkbenchPage } from './WorkbenchPage'

const session_id = '11111111-1111-4111-8111-111111111111'
const service_session_id = '44444444-4444-4444-8444-444444444444'

let request_paths: string[] = []

server.events.on('request:start', ({ request }) => {
  const path = new URL(request.url).pathname
  if (path.startsWith('/api/v1/')) request_paths.push(path)
})

function render_workbench(path: string): void {
  const query_client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={query_client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/workbench/sessions/:session_id" element={<WorkbenchPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function mock_download(): { anchor_click: ReturnType<typeof vi.spyOn> } {
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-export')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined)
  const anchor_click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
  return { anchor_click }
}

function export_ok_handler(): void {
  server.use(
    http.get(`/api/v1/sessions/${session_id}/export`, () =>
      HttpResponse.text('# Nginx 5xx 排查', {
        status: 200,
        headers: {
          'Content-Type': 'text/markdown; charset=utf-8',
          'Content-Disposition': `attachment; filename="opermind-session-${session_id}.md"`,
          'X-Request-Id': 'export-test-ok',
        },
      }),
    ),
  )
}

describe('会话导出入口', () => {
  beforeEach(() => {
    request_paths = []
    window.sessionStorage.clear()
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('点击导出下载安全摘要文档并提示已导出', async () => {
    const { anchor_click } = mock_download()
    render_workbench(`/workbench/sessions/${session_id}`)

    const export_button = await screen.findByRole('button', { name: '导出' })
    fireEvent.click(export_button)

    await waitFor(() => expect(anchor_click).toHaveBeenCalledTimes(1))
    expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob))
    expect(await screen.findByText('会话文档已导出')).toBeInTheDocument()
  })

  it('导出失败展示错误并可重试', async () => {
    const { anchor_click } = mock_download()
    server.use(
      http.get(`/api/v1/sessions/${session_id}/export`, () =>
        HttpResponse.json(
          { error: { code: 'EXPORT_UNAVAILABLE', message: '会话导出暂时不可用，请稍后重试。', details: null } },
          { status: 503, headers: { 'X-Request-Id': 'export-test-fail' } },
        ),
      ),
    )
    render_workbench(`/workbench/sessions/${session_id}`)

    const export_button = await screen.findByRole('button', { name: '导出' })
    fireEvent.click(export_button)

    expect(await screen.findByText(/EXPORT_UNAVAILABLE/)).toBeInTheDocument()
    expect(anchor_click).not.toHaveBeenCalled()

    export_ok_handler()
    fireEvent.click(screen.getByRole('button', { name: '重试' }))

    await waitFor(() => expect(anchor_click).toHaveBeenCalledTimes(1))
  })

  it('空会话提示无可导出内容且不发起导出请求', async () => {
    render_workbench(`/workbench/sessions/${service_session_id}`)
    // 等待消息与 Run 列表加载完成（空会话显示诚实空态提示）。
    await screen.findByText('该会话还没有可恢复的对话内容')

    request_paths = []
    fireEvent.click(screen.getByRole('button', { name: '导出' }))

    expect(await screen.findByText('该会话无可导出内容')).toBeInTheDocument()
    expect(request_paths).not.toContain(`/api/v1/sessions/${service_session_id}/export`)
  })
})
