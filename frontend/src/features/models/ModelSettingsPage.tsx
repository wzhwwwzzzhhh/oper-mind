import { useEffect, useState } from 'react'
import type { FormEvent, ReactElement } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  api_v1_query_keys,
  activate_model_provider_mutation,
  create_model_provider_mutation,
  delete_model_provider_mutation,
  get_model_config_query,
  list_model_providers_query,
  list_provider_models_mutation,
  update_model_mode_mutation,
  update_model_params_mutation,
  update_model_provider_mutation,
  verify_model_provider_mutation,
} from '../../api/v1/queries'
import type { ModelProviderResource } from '../../api/v1/client'
import { Icon } from '../shell/Icon'

interface ProviderFormState {
  name: string
  base_url: string
  model: string
  api_key: string
}

interface ModelParamsFormState {
  temperature: number | null
  max_tokens: number | null
}

type ModelsStatus = 'idle' | 'loading' | 'ok' | 'failed'

const empty_form: ProviderFormState = { name: '', base_url: '', model: '', api_key: '' }
const empty_params: ModelParamsFormState = { temperature: null, max_tokens: null }

function endpoint_label(endpoint: ModelProviderResource['active_endpoint']): string | null {
  if (endpoint === 'diagnostic') return '诊断生效'
  if (endpoint === 'judge') return '裁判生效'
  return null
}

function verify_label(status: ModelProviderResource['verify_status']): string {
  if (status === 'ok') return '连接正常'
  if (status === 'failed') return '连接失败'
  if (status === 'timeout') return '连接超时'
  return '未验证'
}

function models_error_message(error_code: string | null): string {
  switch (error_code) {
    case 'TIMEOUT': return '连接超时，请稍后重试'
    case 'CONNECTION_FAILED': return '无法连接 Provider 服务'
    case 'HTTP_401':
    case 'HTTP_403': return '鉴权失败，请检查 API Key'
    case 'HTTP_404': return '服务未返回模型列表，请检查 Base URL'
    case 'NO_API_KEY': return '未配置 API Key，保存 API Key 后再枚举'
    case 'SECRET_KEY_NOT_CONFIGURED': return '加密主密钥未配置'
    case 'KEY_DECRYPT_FAILED': return '无法解密已保存的 API Key'
    case 'MODELS_PARSE_FAILED': return '服务返回了无法解析的响应'
    case 'INVALID_URL':
    case 'DNS_RESOLUTION_FAILED':
    case 'PRIVATE_ADDRESS_REJECTED': return '地址校验失败'
    default: return error_code != null && error_code.startsWith('HTTP_')
      ? `服务返回 HTTP ${error_code.slice('HTTP_'.length)}`
      : (error_code != null ? `枚举失败（${error_code}）` : '枚举失败')
  }
}

/** 模型服务页：Provider 真实配置管理（掩码展示 / 验证 / 激活 / 编辑 / 删除）。 */
export function ModelSettingsPage(): ReactElement {
  const navigate = useNavigate()
  const query_client = useQueryClient()
  const model_config_query = useQuery({ ...get_model_config_query() })
  const providers_query = useQuery({ ...list_model_providers_query() })
  const [toast, set_toast] = useState<string | null>(null)
  const [form_open, set_form_open] = useState(false)
  const [editing, set_editing] = useState<ModelProviderResource | null>(null)
  const [form, set_form] = useState<ProviderFormState>(empty_form)
  const [deleting, set_deleting] = useState<ModelProviderResource | null>(null)
  const [clear_key, set_clear_key] = useState(false)
  const [mode_selection, set_mode_selection] = useState<'mock' | 'real'>('mock')
  const [models_status, set_models_status] = useState<ModelsStatus>('idle')
  const [model_options, set_model_options] = useState<string[]>([])
  const [models_error, set_models_error] = useState<string | null>(null)
  const [params_form, set_params_form] = useState<ModelParamsFormState>(empty_params)

  const show_toast = (message: string): void => {
    set_toast(message)
    window.setTimeout(() => set_toast(null), 1800)
  }

  const refresh = (): void => {
    void query_client.invalidateQueries({ queryKey: api_v1_query_keys.model_providers() })
    void query_client.invalidateQueries({ queryKey: api_v1_query_keys.model_config() })
  }

  const create_mutation = useMutation({
    ...create_model_provider_mutation(),
    onSuccess: () => {
      set_form_open(false)
      set_form(empty_form)
      refresh()
      show_toast('Provider 已保存。')
    },
    onError: (error) => show_toast(error instanceof Error ? error.message : '保存 Provider 失败。'),
  })

  const update_mutation = useMutation({
    ...update_model_provider_mutation(),
    onSuccess: () => {
      set_form_open(false)
      set_editing(null)
      set_form(empty_form)
      refresh()
      show_toast('Provider 已更新。')
    },
    onError: (error) => show_toast(error instanceof Error ? error.message : '更新 Provider 失败。'),
  })

  const activate_mutation = useMutation({
    ...activate_model_provider_mutation(),
    onSuccess: () => {
      refresh()
      show_toast('已切换生效配置。')
    },
    onError: (error) => show_toast(error instanceof Error ? error.message : '激活 Provider 失败。'),
  })

  const verify_mutation = useMutation({
    ...verify_model_provider_mutation(),
    onSuccess: () => {
      refresh()
      show_toast('连接验证已完成。')
    },
    onError: (error) => show_toast(error instanceof Error ? error.message : '连接验证失败。'),
  })

  const models_mutation = useMutation({
    ...list_provider_models_mutation(),
    onMutate: () => set_models_status('loading'),
    onSuccess: (response) => {
      const result = response.data
      if (result.status === 'ok') {
        set_models_status('ok')
        set_model_options(result.models ?? [])
        set_models_error(null)
      } else {
        set_models_status('failed')
        set_model_options([])
        set_models_error(models_error_message(result.error_code))
      }
    },
    onError: (error) => {
      set_models_status('failed')
      set_model_options([])
      set_models_error(error instanceof Error ? error.message : '枚举模型列表失败。')
    },
  })

  const refresh_models = (): void => {
    if (editing != null) {
      models_mutation.mutate(editing.id)
    }
  }

  const delete_mutation = useMutation({
    ...delete_model_provider_mutation(),
    onSuccess: () => {
      set_deleting(null)
      refresh()
      show_toast('Provider 已删除。')
    },
    onError: (error) => show_toast(error instanceof Error ? error.message : '删除 Provider 失败。'),
  })

  const mode_mutation = useMutation({
    ...update_model_mode_mutation(),
    onSuccess: (response) => {
      const config = response.data.config
      query_client.setQueryData(api_v1_query_keys.model_config(), response)
      set_mode_selection(config.mode)
      show_toast(config.mode === 'real' && !config.mode_available ? 'real 模式已保存但当前不可用。' : `运行模式已切换为 ${config.mode === 'mock' ? 'Mock' : '真实调用'}。`)
    },
    onError: (error) => show_toast(error instanceof Error ? error.message : '切换运行模式失败。'),
  })

  const params_mutation = useMutation({
    ...update_model_params_mutation(),
    onSuccess: (response) => {
      const params = response.data.config.params
      query_client.setQueryData(api_v1_query_keys.model_config(), response)
      set_params_form({ temperature: params.temperature, max_tokens: params.max_tokens })
      show_toast('运行参数已保存。')
    },
    onError: (error) => show_toast(error instanceof Error ? error.message : '保存运行参数失败。'),
  })

  const set_params_field = (field: keyof ModelParamsFormState, raw: string): void => {
    set_params_form((current) => {
      if (raw === '') {
        return { ...current, [field]: null }
      }
      const value = Number(raw)
      return { ...current, [field]: Number.isFinite(value) ? value : null }
    })
  }

  const reset_models_picker = (): void => {
    set_models_status('idle')
    set_model_options([])
    set_models_error(null)
  }

  const open_create = (): void => {
    set_editing(null)
    set_form(empty_form)
    set_clear_key(false)
    reset_models_picker()
    set_form_open(true)
  }

  const open_edit = (provider: ModelProviderResource): void => {
    set_editing(provider)
    set_form({ name: provider.name, base_url: provider.base_url, model: provider.model, api_key: '' })
    set_clear_key(false)
    reset_models_picker()
    set_form_open(true)
  }

  const submit_form = (event: FormEvent): void => {
    event.preventDefault()
    const name = form.name.trim()
    const base_url = form.base_url.trim()
    const model = form.model.trim()
    const api_key = editing != null && clear_key ? '' : (form.api_key === '' ? null : form.api_key)
    if (editing != null) {
      update_mutation.mutate({ provider_id: editing.id, name, base_url, model, api_key })
    } else {
      create_mutation.mutate({ name, base_url, model, api_key, idempotency_key: globalThis.crypto.randomUUID() })
    }
  }

  const set_form_field = (field: keyof ProviderFormState, value: string): void => {
    set_form((current) => ({ ...current, [field]: value }))
  }

  const config = model_config_query.data?.data.config
  const diagnostic = config?.diagnostic_model
  const judge = config?.judge_model
  const providers = providers_query.data?.data.items ?? []
  const saving = create_mutation.isPending || update_mutation.isPending

  useEffect(() => {
    if (config != null) {
      set_mode_selection(config.mode)
    }
  }, [config])

  useEffect(() => {
    if (config != null) {
      set_params_form({ temperature: config.params.temperature, max_tokens: config.params.max_tokens })
    }
  }, [config])

  return (
    <div className="model-page">
      <div className="model-breadcrumb"><button onClick={() => navigate('/workbench')} type="button">会话工作台</button><span>/</span><strong>模型服务</strong></div>

      <section className="model-page-head">
        <div><div className="model-eyebrow">工作台配置</div><h1>模型服务</h1><p>管理模型 Provider 与 API Key。Key 加密保存、掩码展示，绝不回显明文。</p></div>
        <div className="model-head-actions"><button className="model-button" onClick={() => { void providers_query.refetch(); show_toast('已刷新 Provider 列表。') }} type="button">刷新列表</button><button className="model-button primary" onClick={open_create} type="button">＋ 添加模型服务</button></div>
      </section>

      {model_config_query.isPending && <div className="model-inline-state">正在读取当前生效配置…</div>}
      {model_config_query.isError && <div className="model-inline-state error">暂时无法读取模型配置，请稍后重试。</div>}
      {providers_query.isError && <div className="model-inline-state error">暂时无法读取 Provider 列表，请稍后重试。</div>}

      <section className="model-summary">
        <article><small>诊断模型</small><strong>{diagnostic?.model ?? '未配置'}</strong><span>{diagnostic ? diagnostic.provider : '后端未返回配置'}</span></article>
        <article><small>裁判模型</small><strong>{judge?.model ?? '未配置'}</strong><span>{judge ? judge.provider : '未配置独立裁判模型'}</span></article>
        <article><small>运行模式</small><strong>{config == null ? '未知' : config.mode === 'mock' ? 'Mock' : '真实调用'}</strong><span>{config == null ? '后端未返回配置' : config.mode === 'mock' ? '返回确定性样例，不出网' : '按生效 Provider 真实调用'}</span></article>
        <article><small>已配置 Provider</small><strong>{providers_query.isSuccess ? providers.length : '—'} <em>个</em></strong><span>{providers_query.isSuccess ? '来自后端安全视图' : '尚未读取到列表'}</span></article>
      </section>

      <section className="model-section" id="mode">
        <div className="model-section-head"><div><h2>运行模式</h2><p>切换 mock / real 模式并保存，保存后下一次会话立即生效，无需重启。模式选择持久化在后端，重启后保持。</p></div></div>
        <div className="model-card boundary-card">
          {config == null
            ? <div className="model-inline-state">正在读取当前生效配置…</div>
            : (
              <>
                <div className="mode-switch-row">
                  <div className="mode-switch-options">
                    <button className={`mode-option ${mode_selection === 'mock' ? 'selected' : ''}`} onClick={() => set_mode_selection('mock')} disabled={mode_mutation.isPending} type="button">
                      <strong>Mock</strong><span>返回确定性样例，不出网，零消耗</span>
                    </button>
                    <button className={`mode-option ${mode_selection === 'real' ? 'selected' : ''}`} onClick={() => set_mode_selection('real')} disabled={mode_mutation.isPending} type="button">
                      <strong>真实调用</strong><span>按生效 Provider 真实调用</span>
                    </button>
                  </div>
                  <button className="model-button primary" onClick={() => mode_mutation.mutate({ mode: mode_selection })} disabled={mode_mutation.isPending || mode_selection === config.mode} type="button">保存模式</button>
                </div>
                {config.mode === 'real' && !config.mode_available && (
                  <div className="mode-unavailable">real 模式已保存但当前不可用：{config.mode_unavailable_reason ?? '无可用 Provider/API Key'}。请先在下方配置并激活带 API Key 的 Provider，或切回 Mock。</div>
                )}
              </>
            )}
        </div>
      </section>

      <section className="model-section" id="params">
        <div className="model-section-head"><div><h2>运行参数</h2><p>配置真实进入调用链的模型参数（temperature / max_tokens），保存后下一次会话立即生效。未配置时用后端默认值；留空输入可恢复默认。参数仅对 real 内容生成调用生效，路由与裁决保持确定性 0.0。</p></div></div>
        <div className="model-card boundary-card">
          {config == null
            ? <div className="model-inline-state">正在读取当前生效配置…</div>
            : (
              <>
                <div className="params-row">
                  <label className="params-field">
                    <span>temperature <em>（0–2）</em></span>
                    <input aria-label="temperature" min={0} max={2} step={0.1} type="number" value={params_form.temperature ?? ''} onChange={(event) => set_params_field('temperature', event.target.value)} />
                    <small>{params_form.temperature != null ? `已配置：${params_form.temperature}` : `未配置，默认 ${config.params_defaults.temperature}（确定性）`}</small>
                  </label>
                  <label className="params-field">
                    <span>max_tokens <em>（正整数）</em></span>
                    <input aria-label="max_tokens" min={1} max={102400} type="number" value={params_form.max_tokens ?? ''} onChange={(event) => set_params_field('max_tokens', event.target.value)} />
                    <small>{params_form.max_tokens != null ? `已配置：${params_form.max_tokens}` : '未配置，不限制（用模型默认）'}</small>
                  </label>
                  <button className="model-button primary params-save" onClick={() => params_mutation.mutate({ temperature: params_form.temperature, max_tokens: params_form.max_tokens })} disabled={params_mutation.isPending} type="button">保存参数</button>
                </div>
                {config.mode === 'mock' && <div className="mode-unavailable">当前为 mock 模式，参数不生效；切换 real 后保存的参数立即进入调用链。</div>}
              </>
            )}
        </div>
      </section>

      <section className="model-section" id="providers">
        <div className="model-section-head"><div><h2>已配置 Provider</h2><p>来自后端安全视图；API Key 掩码展示，可验证连接、切换为生效配置或删除。</p></div></div>
        {providers_query.isPending && <div className="model-inline-state">正在读取 Provider 列表…</div>}
        {providers_query.isSuccess && providers.length === 0 && <div className="model-inline-state">尚未配置 Provider。点击「＋ 添加模型服务」接入你的大模型服务。</div>}
        <div className="model-provider-list">{providers.map((provider) => (
          <article className="model-provider" key={provider.id}>
            <div className="provider-logo provider-gateway">{provider.name.slice(0, 1).toUpperCase()}</div>
            <div className="provider-main">
              <strong>{provider.name}</strong>
              <span>{provider.base_url} · {provider.model}</span>
              <div className="provider-tags">
                <i>{provider.has_api_key ? `Key 已配置 · ${provider.masked_tail != null ? `末 ${provider.masked_tail}` : '密文'}` : '未配置 Key'}</i>
                <i>{verify_label(provider.verify_status)}{provider.verify_error_code != null ? ` · ${provider.verify_error_code}` : ''}</i>
              </div>
            </div>
            <div className="provider-meta">
              <small>生效状态</small>
              <b className={`provider-state ${endpoint_label(provider.active_endpoint) != null ? 'sample' : 'muted'}`}>{endpoint_label(provider.active_endpoint) ?? '未启用'}</b>
              <span>{provider.active_endpoint != null ? '当前会话链路使用' : '未设为生效配置'}</span>
            </div>
            <div className="provider-actions">
              <button className="model-link" onClick={() => verify_mutation.mutate(provider.id)} disabled={verify_mutation.isPending} type="button">验证连接</button>
              <button className="model-link" onClick={() => activate_mutation.mutate({ provider_id: provider.id, endpoint: 'diagnostic' })} disabled={activate_mutation.isPending || provider.active_endpoint === 'diagnostic'} type="button">设为诊断</button>
              <button className="model-link" onClick={() => activate_mutation.mutate({ provider_id: provider.id, endpoint: 'judge' })} disabled={activate_mutation.isPending || provider.active_endpoint === 'judge'} type="button">设为裁判</button>
              <button className="model-link" onClick={() => open_edit(provider)} type="button">编辑</button>
              <button className="model-link" onClick={() => set_deleting(provider)} type="button">删除</button>
            </div>
          </article>
        ))}</div>
      </section>

      <section className="model-section" id="security">
        <div className="model-section-head"><div><h2>运行边界</h2><p>模型角色不能绕过 Agent、Tool Gateway 和审批策略。</p></div></div>
        <div className="model-card boundary-card">
          <ul>
            <li>Coordinator 只负责路由，不直接获得任意服务访问权</li>
            <li>DB / Server / Log Agent 只能调用各自注册的受控 Tool</li>
            <li>Tool 调用进入后端网关，Trace 只展示安全摘要</li>
            <li>Debate、Reflection、Report 只处理结构化诊断结果</li>
            <li>高风险动作仍需提案、审批、白名单执行和验证</li>
          </ul>
          <div className="boundary-note">Provider 与 API Key 在此页管理；Key 加密存储、掩码展示，明文不进日志、Trace 或接口响应。</div>
        </div>
      </section>

      {form_open && <div className="model-modal" role="dialog" aria-modal="true" aria-labelledby="model-modal-title"><div className="model-dialog">
        <div className="model-dialog-head"><div><strong id="model-modal-title">{editing != null ? `编辑 ${editing.name}` : '添加模型服务'}</strong><p>{editing != null ? '修改名称、Base URL、模型；API Key 留空保持不变，空串清除。' : '填写 OpenAI-compatible Provider 信息，保存时加密存储 API Key。'}</p></div><button aria-label="关闭" className="icon-btn" onClick={() => { set_form_open(false); set_editing(null); }} type="button"><Icon name="x" size={14} /></button></div>
        <form className="provider-form" onSubmit={submit_form}>
          <label>名称<input aria-label="Provider 名称" required value={form.name} onChange={(event) => set_form_field('name', event.target.value)} type="text" placeholder="如 DeepSeek 生产" /></label>
          <label>Base URL<input aria-label="Base URL" required value={form.base_url} onChange={(event) => set_form_field('base_url', event.target.value)} type="url" placeholder="https://api.deepseek.com/v1" /></label>
          <label>模型
            <div className="model-field-row">
              <input aria-label="模型" required value={form.model} onChange={(event) => set_form_field('model', event.target.value)} type="text" placeholder="deepseek-chat" />
              <button className="model-button" type="button" onClick={refresh_models} disabled={editing == null || models_mutation.isPending}>刷新模型列表</button>
            </div>
            {editing == null && <small className="model-inline-state">保存 Provider 后可刷新模型列表。</small>}
            {models_status === 'ok' && model_options.length > 0 && (
              <select aria-label="选择模型" className="model-models-select" value={form.model} onChange={(event) => set_form_field('model', event.target.value)}>
                {editing != null && form.model !== '' && !model_options.includes(form.model) && (
                  <option value={form.model}>{form.model}（当前值）</option>
                )}
                {model_options.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            )}
            {models_status === 'ok' && model_options.length === 0 && <small className="model-inline-state">该 Provider 未返回可用模型。</small>}
            {models_status === 'failed' && <div className="model-inline-state error">{models_error}</div>}
          </label>
          <label>API Key<input aria-label="API Key" value={form.api_key} onChange={(event) => set_form_field('api_key', event.target.value)} type="password" autoComplete="off" placeholder={editing != null ? '留空保持不变' : '可选，未配置时仅保存元数据'} /></label>
          {editing != null && editing.has_api_key && <label className="provider-clear-key"><input aria-label="清除已保存的 API Key" type="checkbox" checked={clear_key} onChange={(event) => set_clear_key(event.target.checked)} /> 清除已保存的 API Key</label>}
          <div className="model-dialog-footer"><button className="model-button" type="button" onClick={() => { set_form_open(false); set_editing(null); }}>取消</button><button className="model-button primary" type="submit" disabled={saving}>{editing != null ? '保存修改' : '保存 Provider'}</button></div>
        </form>
      </div></div>}

      {deleting != null && <div className="model-modal" role="dialog" aria-modal="true" aria-labelledby="model-delete-title"><div className="model-dialog">
        <div className="model-dialog-head"><div><strong id="model-delete-title">删除 Provider</strong><p>将删除「{deleting.name}」及其 API Key 密文。若为生效配置，删除后该端点回退 env/YAML 兜底。</p></div><button aria-label="关闭" className="icon-btn" onClick={() => set_deleting(null)} type="button"><Icon name="x" size={14} /></button></div>
        <div className="model-dialog-footer"><button className="model-button" type="button" onClick={() => set_deleting(null)}>取消</button><button className="model-button primary" type="button" onClick={() => delete_mutation.mutate(deleting.id)} disabled={delete_mutation.isPending}>确认删除</button></div>
      </div></div>}

      {toast && <div className="model-toast" role="status">{toast}</div>}
    </div>
  )
}
