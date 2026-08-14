import { fireEvent, render, screen } from '@testing-library/react'
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
  it('读取真实配置并展示 Provider 掩码视图', async () => {
    open_models()
    render(<App />)

    expect((await screen.findAllByText('diagnostic-model')).length).toBeGreaterThan(0)
    expect(screen.getByText('未配置独立裁判模型')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '＋ 添加模型服务' })).toBeEnabled()
    expect(await screen.findByText('DeepSeek 生产')).toBeInTheDocument()
    expect(screen.getByText(/Key 已配置/)).toBeInTheDocument()
    expect(screen.getByText(/末 1234/)).toBeInTheDocument()
    expect(screen.queryByText(/sk-test/)).not.toBeInTheDocument()
  })

  it('打开添加表单并保存 Provider', async () => {
    open_models()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '＋ 添加模型服务' }))
    expect(await screen.findByLabelText('Provider 名称')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Provider 名称'), { target: { value: 'New Provider' } })
    fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'https://api.example.com/v1' } })
    fireEvent.change(screen.getByLabelText('模型'), { target: { value: 'model-x' } })
    fireEvent.change(screen.getByLabelText('API Key'), { target: { value: 'sk-test-12345678' } })

    fireEvent.click(screen.getByRole('button', { name: '保存 Provider' }))

    expect(await screen.findByText('Provider 已保存。')).toBeInTheDocument()
    expect(screen.queryByLabelText('Provider 名称')).not.toBeInTheDocument()
  })

  it('验证连接并提示完成', async () => {
    open_models()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '验证连接' }))

    expect(await screen.findByText('连接验证已完成。')).toBeInTheDocument()
  })

  it('切换为生效配置并提示完成', async () => {
    open_models()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '设为诊断' }))

    expect(await screen.findByText('已切换生效配置。')).toBeInTheDocument()
  })

  it('删除 Provider 需二次确认', async () => {
    open_models()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '删除' }))
    expect(await screen.findByText(/将删除/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '确认删除' }))

    expect(await screen.findByText('Provider 已删除。')).toBeInTheDocument()
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

  it('切换到 real 保存后如实提示不可用', async () => {
    open_models()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /真实调用/ }))
    fireEvent.click(screen.getByRole('button', { name: '保存模式' }))

    expect(await screen.findByText(/请先在下方配置并激活带 API Key 的 Provider/)).toBeInTheDocument()
    expect(screen.getAllByText(/real 模式已保存但当前不可用/).length).toBeGreaterThan(0)
  })

  it('切回 mock 后显示确定性样例说明', async () => {
    open_models()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: /真实调用/ }))
    fireEvent.click(screen.getByRole('button', { name: '保存模式' }))
    expect(await screen.findByText(/请先在下方配置并激活带 API Key 的 Provider/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Mock/ }))
    fireEvent.click(screen.getByRole('button', { name: '保存模式' }))

    expect(await screen.findByText('运行模式已切换为 Mock。')).toBeInTheDocument()
  })

  it('编辑 Provider 时刷新模型列表并选择模型', async () => {
    open_models()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '编辑' }))
    fireEvent.click(await screen.findByRole('button', { name: '刷新模型列表' }))

    const select = await screen.findByLabelText('选择模型')
    fireEvent.change(select, { target: { value: 'deepseek-reasoner' } })

    expect(screen.getByLabelText('模型')).toHaveValue('deepseek-reasoner')
  })

  it('刷新模型列表失败时展示脱敏原因', async () => {
    server.use(
      http.get('/api/v1/model/providers/:provider_id/models', () =>
        HttpResponse.json(
          {
            provider_id: 'p',
            status: 'failed',
            models: null,
            error_code: 'HTTP_401',
            meta: { request_id: 'r' },
          },
          { status: 200, headers: { 'X-Request-Id': 'r' } },
        ),
      ),
    )
    open_models()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '编辑' }))
    fireEvent.click(await screen.findByRole('button', { name: '刷新模型列表' }))

    expect(await screen.findByText(/鉴权失败，请检查 API Key/)).toBeInTheDocument()
  })

  it('新建态刷新按钮禁用并提示先保存', async () => {
    open_models()
    render(<App />)

    fireEvent.click(await screen.findByRole('button', { name: '＋ 添加模型服务' }))
    expect(await screen.findByLabelText('Provider 名称')).toBeInTheDocument()

    expect(screen.getByRole('button', { name: '刷新模型列表' })).toBeDisabled()
    expect(screen.getByText(/保存 Provider 后可刷新模型列表/)).toBeInTheDocument()
  })

  it('未配置参数时展示默认值标注', async () => {
    open_models()
    render(<App />)

    expect(await screen.findByText(/未配置，默认 0（确定性）/)).toBeInTheDocument()
    expect(screen.getByText(/未配置，不限制（用模型默认）/)).toBeInTheDocument()
  })

  it('保存运行参数后展示已配置值', async () => {
    open_models()
    render(<App />)

    const temperature = await screen.findByLabelText('temperature')
    fireEvent.change(temperature, { target: { value: '0.5' } })
    fireEvent.change(screen.getByLabelText('max_tokens'), { target: { value: '4096' } })
    fireEvent.click(screen.getByRole('button', { name: '保存参数' }))

    expect(await screen.findByText('运行参数已保存。')).toBeInTheDocument()
    expect(await screen.findByText('已配置：0.5')).toBeInTheDocument()
    expect(screen.getByText('已配置：4096')).toBeInTheDocument()
  })

  it('mock 模式标注参数仅 real 生效', async () => {
    open_models()
    render(<App />)

    expect(await screen.findByText(/当前为 mock 模式，参数不生效/)).toBeInTheDocument()
  })
})
