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
  update_model_provider_mutation,
  verify_model_provider_mutation,
} from '../../api/v1/queries'
import type { ModelProviderResource } from '../../api/v1/client'

type PolicyKey = 'coordinator' | 'db' | 'server' | 'log' | 'debate' | 'reflection' | 'report'

interface ModelItem {
  id: string
  name: string
  provider: string
  description: string
  tags: string[]
}

interface AgentPolicy {
  key: PolicyKey
  name: string
  description: string
  model: string
}

interface ProviderFormState {
  name: string
  base_url: string
  model: string
  api_key: string
}

const models: ModelItem[] = [
  { id: 'deepseek-reasoner', name: 'DeepSeek Reasoner', provider: 'DeepSeek · 云端示例', description: '适合复杂问题分析、证据汇总和需要多步推理的调查。', tags: ['推理', '工具调用', '流式输出'] },
  { id: 'deepseek-chat', name: 'DeepSeek Chat', provider: 'DeepSeek · 云端示例', description: '适合普通会话、快速问答和调查报告整理。', tags: ['对话', '工具调用', '流式输出'] },
  { id: 'qwen3-8b', name: 'qwen3:8b', provider: 'Ollama · 本地示例', description: '本地开发模型，数据不离开当前环境；工具调用能力待验证。', tags: ['本地', '流式输出', '未验证'] },
  { id: 'gpt-4-1', name: 'gpt-4.1', provider: '公司网关 · 示例模型', description: '适合稳定工具调用的调查任务；当前网关连接能力待确认。', tags: ['对话', '工具调用', '需确认'] },
  { id: 'llama3-2', name: 'llama3.2:latest', provider: 'Ollama · 本地示例', description: '本地通用模型，适合开发环境中的基础对话验证。', tags: ['本地', '对话'] },
  { id: 'deepseek-r1-14b', name: 'deepseek-r1:14b', provider: 'Ollama · 本地示例', description: '本地推理模型，适合不出网环境中的复杂问题试验。', tags: ['本地', '推理', '未验证'] },
]

const default_policy: Record<PolicyKey, boolean> = {
  coordinator: true,
  db: true,
  server: true,
  log: true,
  debate: true,
  reflection: true,
  report: true,
}

const agent_policies: AgentPolicy[] = [
  { key: 'coordinator', name: 'Coordinator', description: '动态路由、串行/并行编排', model: 'DeepSeek Reasoner' },
  { key: 'db', name: 'DB Agent', description: '慢 SQL、索引与数据库事实', model: 'DeepSeek Reasoner' },
  { key: 'server', name: 'Server Agent', description: 'CPU、内存、磁盘、进程、网络', model: 'DeepSeek Chat' },
  { key: 'log', name: 'Log Agent', description: '错误日志、异常模式、慢查询日志', model: 'DeepSeek Chat' },
  { key: 'debate', name: 'Debate Arena', description: '多 Agent 分歧裁决与证据对比', model: 'DeepSeek Reasoner' },
  { key: 'reflection', name: 'Reflection Engine', description: '报告复审与问题反馈', model: 'DeepSeek Chat' },
  { key: 'report', name: 'Report Agent', description: '结构化诊断报告与综合结论', model: 'DeepSeek Chat' },
]

const empty_form: ProviderFormState = { name: '', base_url: '', model: '', api_key: '' }

function read_local<T>(key: string, fallback: T): T {
  try {
    const value = window.localStorage.getItem(key)
    return value ? JSON.parse(value) as T : fallback
  } catch {
    return fallback
  }
}

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

/** 模型服务页：Provider 真实配置管理（掩码展示 / 验证 / 激活 / 编辑 / 删除）；本地策略仍只属于 UI 偏好。 */
export function ModelSettingsPage(): ReactElement {
  const navigate = useNavigate()
  const query_client = useQueryClient()
  const model_config_query = useQuery({ ...get_model_config_query() })
  const providers_query = useQuery({ ...list_model_providers_query() })
  const [policy, set_policy] = useState<Record<PolicyKey, boolean>>(() => ({ ...default_policy, ...read_local('opermind:model-policy', {}) }))
  const [current_model, set_current_model] = useState(() => read_local('opermind:model-current', 'deepseek-reasoner'))
  const [toast, set_toast] = useState<string | null>(null)
  const [form_open, set_form_open] = useState(false)
  const [editing, set_editing] = useState<ModelProviderResource | null>(null)
  const [form, set_form] = useState<ProviderFormState>(empty_form)
  const [deleting, set_deleting] = useState<ModelProviderResource | null>(null)
  const [clear_key, set_clear_key] = useState(false)

  useEffect(() => { window.localStorage.setItem('opermind:model-policy', JSON.stringify(policy)) }, [policy])
  useEffect(() => { window.localStorage.setItem('opermind:model-current', current_model) }, [current_model])

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

  const delete_mutation = useMutation({
    ...delete_model_provider_mutation(),
    onSuccess: () => {
      set_deleting(null)
      refresh()
      show_toast('Provider 已删除。')
    },
    onError: (error) => show_toast(error instanceof Error ? error.message : '删除 Provider 失败。'),
  })

  const open_create = (): void => {
    set_editing(null)
    set_form(empty_form)
    set_clear_key(false)
    set_form_open(true)
  }

  const open_edit = (provider: ModelProviderResource): void => {
    set_editing(provider)
    set_form({ name: provider.name, base_url: provider.base_url, model: provider.model, api_key: '' })
    set_clear_key(false)
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

  const current = models.find((item) => item.id === current_model) ?? models[0]
  const enabled_count = Object.values(policy).filter(Boolean).length
  const config = model_config_query.data?.data.config
  const diagnostic = config?.diagnostic_model
  const judge = config?.judge_model
  const providers = providers_query.data?.data.items ?? []
  const saving = create_mutation.isPending || update_mutation.isPending

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
        <article><small>诊断模型</small><strong>{diagnostic?.model ?? '未配置'}</strong><span>{diagnostic ? `${diagnostic.provider} · ${config?.mode === 'mock' ? 'Mock 模式' : '真实模式'}` : '后端未返回配置'}</span></article>
        <article><small>裁判模型</small><strong>{judge?.model ?? '未配置'}</strong><span>{judge ? judge.provider : '未配置独立裁判模型'}</span></article>
        <article><small>本地偏好</small><strong>{current.name}</strong><span>仅影响当前页面，不改变后端配置</span></article>
        <article><small>Agent 策略</small><strong>{enabled_count} <em>项开启</em></strong><span>仅保存本地 UI 偏好</span></article>
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

      {model_config_query.isSuccess && <section className="model-section" id="models">
        <div className="model-section-head"><div><h2>本地页面偏好</h2><p>选择仅用于页面展示的本地偏好，不会写入或改变后端生效配置。</p></div><button className="model-link" disabled type="button">刷新模型列表未启用 →</button></div>
        <div className="model-grid">{models.map((item) => <article className={`model-card${current_model === item.id ? ' selected' : ''}`} key={item.id}><div className="model-card-head"><div><strong>{item.name}</strong><small>{item.provider}</small></div>{current_model === item.id && <span className="default-mark">当前偏好</span>}</div><p>{item.description}</p><div className="model-tags">{item.tags.map((tag) => <i key={tag}>{tag}</i>)}</div><button className="model-card-action" onClick={() => { set_current_model(item.id); show_toast(`已将 ${item.name} 设为本地偏好。`) }} type="button">{current_model === item.id ? '当前选择' : '设为当前偏好'}</button></article>)}</div>
      </section>}

      <section className="model-section" id="policy">
        <div className="model-section-head"><div><h2>Agent 调用策略</h2><p>对应当前项目 Coordinator、领域 Agent 和质量保障组件；开关仅保存到本地。</p></div><button className="model-link" onClick={() => { set_policy({ ...default_policy }); show_toast('Agent 策略已恢复默认。') }} type="button">恢复默认 →</button></div>
        <div className="model-policy-layout"><div className="model-card policy-card"><div className="model-card-title"><h3>Agent 与任务路由</h3><p>本页面不改变后端 Coordinator 的真实装配。</p></div>{agent_policies.map((item) => <div className="policy-row" key={item.key}><div><strong>{item.name}</strong><small>{item.description}</small></div><span className="policy-model">{item.model}</span><button aria-label={`${item.name} 策略开关`} aria-pressed={policy[item.key]} className={`policy-toggle${policy[item.key] ? ' on' : ''}`} onClick={() => set_policy((current_policy) => ({ ...current_policy, [item.key]: !current_policy[item.key] }))} type="button"><span /></button></div>)}</div><div className="model-card boundary-card" id="security"><div className="model-card-title"><h3>运行边界</h3><p>模型角色不能绕过 Agent、Tool Gateway 和审批策略。</p></div><ul><li>Coordinator 只负责路由，不直接获得任意服务访问权</li><li>DB / Server / Log Agent 只能调用各自注册的受控 Tool</li><li>Tool 调用进入后端网关，Trace 只展示安全摘要</li><li>Debate、Reflection、Report 只处理结构化诊断结果</li><li>高风险动作仍需提案、审批、白名单执行和验证</li></ul><div className="boundary-note">Provider 与 API Key 在此页管理；Key 加密存储、掩码展示，明文不进日志、Trace 或接口响应。</div></div></div>
      </section>

      {form_open && <div className="model-modal" role="dialog" aria-modal="true" aria-labelledby="model-modal-title"><div className="model-dialog">
        <div className="model-dialog-head"><div><strong id="model-modal-title">{editing != null ? `编辑 ${editing.name}` : '添加模型服务'}</strong><p>{editing != null ? '修改名称、Base URL、模型；API Key 留空保持不变，空串清除。' : '填写 OpenAI-compatible Provider 信息，保存时加密存储 API Key。'}</p></div><button aria-label="关闭" className="more-button" onClick={() => { set_form_open(false); set_editing(null); }} type="button">×</button></div>
        <form className="provider-form" onSubmit={submit_form}>
          <label>名称<input aria-label="Provider 名称" required value={form.name} onChange={(event) => set_form_field('name', event.target.value)} type="text" placeholder="如 DeepSeek 生产" /></label>
          <label>Base URL<input aria-label="Base URL" required value={form.base_url} onChange={(event) => set_form_field('base_url', event.target.value)} type="url" placeholder="https://api.deepseek.com/v1" /></label>
          <label>模型<input aria-label="模型" required value={form.model} onChange={(event) => set_form_field('model', event.target.value)} type="text" placeholder="deepseek-chat" /></label>
          <label>API Key<input aria-label="API Key" value={form.api_key} onChange={(event) => set_form_field('api_key', event.target.value)} type="password" autoComplete="off" placeholder={editing != null ? '留空保持不变' : '可选，未配置时仅保存元数据'} /></label>
          {editing != null && editing.has_api_key && <label className="provider-clear-key"><input aria-label="清除已保存的 API Key" type="checkbox" checked={clear_key} onChange={(event) => set_clear_key(event.target.checked)} /> 清除已保存的 API Key</label>}
          <div className="model-dialog-footer"><button className="model-button" type="button" onClick={() => { set_form_open(false); set_editing(null); }}>取消</button><button className="model-button primary" type="submit" disabled={saving}>{editing != null ? '保存修改' : '保存 Provider'}</button></div>
        </form>
      </div></div>}

      {deleting != null && <div className="model-modal" role="dialog" aria-modal="true" aria-labelledby="model-delete-title"><div className="model-dialog">
        <div className="model-dialog-head"><div><strong id="model-delete-title">删除 Provider</strong><p>将删除「{deleting.name}」及其 API Key 密文。若为生效配置，删除后该端点回退 env/YAML 兜底。</p></div><button aria-label="关闭" className="more-button" onClick={() => set_deleting(null)} type="button">×</button></div>
        <div className="model-dialog-footer"><button className="model-button" type="button" onClick={() => set_deleting(null)}>取消</button><button className="model-button primary" type="button" onClick={() => delete_mutation.mutate(deleting.id)} disabled={delete_mutation.isPending}>确认删除</button></div>
      </div></div>}

      {toast && <div className="model-toast" role="status">{toast}</div>}
    </div>
  )
}
