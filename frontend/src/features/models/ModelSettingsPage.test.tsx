import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { HttpResponse, http } from 'msw'

import { App } from '../../app/App'
import { server } from '../../test/server'

function open_models(): void {
  window.history.replaceState({}, '', '/models')
}

function error_response(request: Request) {
  const request_id = request.headers.get('X-Request-Id') ?? 'missing-client-request-id'
  return HttpResponse.json(
    { error: { code: 'INTERNAL_ERROR', message: '服务内部错误，请稍后重试', details: null }, meta: { request_id } },
    { status: 500, headers: { 'X-Request-Id': request_id } },
  )
}

describe('ModelSettingsPage', () => {
  it('读取真实配置并展示裁判模型未配置空态', async () => {
    open_models()
    render(<App />)

    expect((await screen.findAllByText('diagnostic-model')).length).toBeGreaterThan(0)
    expect(screen.getByText('未配置独立裁判模型')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '＋ 添加模型服务' })).toBeDisabled()
  })

  it('读取失败时显示错误，不展示静态 Provider 示例', async () => {
    server.use(
      http.get('/api/v1/model/config', ({ request }) => error_response(request)),
    )
    open_models()
    render(<App />)

    expect(await screen.findByText('暂时无法读取模型配置，请稍后重试。')).toBeInTheDocument()
    expect(screen.queryByText('示例配置')).not.toBeInTheDocument()
    expect(screen.queryByText('DeepSeek 官方 API')).not.toBeInTheDocument()
    expect(screen.queryByText('本地页面偏好')).not.toBeInTheDocument()
  })
})
