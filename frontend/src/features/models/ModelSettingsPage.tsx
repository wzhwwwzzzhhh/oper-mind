import { useEffect, useState } from 'react'
import type { ReactElement } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'

import { get_model_config_query } from '../../api/v1/queries'

type PolicyKey = 'coordinator' | 'db' | 'server' | 'log' | 'debate' | 'reflection' | 'report'
type ProviderKey = 'ollama' | 'deepseek' | 'openai' | 'gateway'

interface ProviderItem {
  key: ProviderKey
  short: string
  name: string
  endpoint: string
  tags: string[]
  status: string
  status_class: 'sample' | 'muted' | 'attention'
  note: string
}

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

const providers: ProviderItem[] = [
  { key: 'ollama', short: 'O', name: '本地 Ollama', endpoint: 'localhost:11434 · 本地开发', tags: ['本地', '4 个模型', '流式输出'], status: '示例配置', status_class: 'sample', note: '未连接验证' },
  { key: 'deepseek', short: 'DS', name: 'DeepSeek 官方 API', endpoint: 'api.deepseek.com · 云端服务', tags: ['Chat', 'Reasoner', '工具调用'], status: '示例 Provider', status_class: 'sample', note: '未连接验证' },
  { key: 'openai', short: 'AI', name: 'OpenAI 官方 API', endpoint: 'api.openai.com · 云端服务', tags: ['待添加 API Key'], status: '未配置', status_class: 'muted', note: '没有真实凭据' },
  { key: 'gateway', short: 'GW', name: '公司模型网关', endpoint: 'OpenAI Compatible · 内部服务', tags: ['兼容 API', '3 个模型', '工具调用'], status: '需确认', status_class: 'attention', note: '连接能力待验证' },
]

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

function read_local<T>(key: string, fallback: T): T {
  try {
    const value = window.localStorage.getItem(key)
    return value ? JSON.parse(value) as T : fallback
  } catch {
    return fallback
  }
}

/** 模型服务页：读取后端真实配置，本地策略仍只属于 UI 偏好。 */
export function ModelSettingsPage(): ReactElement {
  const navigate = useNavigate()
  const model_config_query = useQuery({ ...get_model_config_query() })
  const [policy, set_policy] = useState<Record<PolicyKey, boolean>>(() => ({ ...default_policy, ...read_local('opermind:model-policy', {}) }))
  const [current_model, set_current_model] = useState(() => read_local('opermind:model-current', 'deepseek-reasoner'))
  const [modal_open, set_modal_open] = useState(false)
  const [selected_provider, set_selected_provider] = useState<ProviderKey>('ollama')
  const [toast, set_toast] = useState<string | null>(null)

  useEffect(() => { window.localStorage.setItem('opermind:model-policy', JSON.stringify(policy)) }, [policy])
  useEffect(() => { window.localStorage.setItem('opermind:model-current', current_model) }, [current_model])

  const show_toast = (message: string): void => {
    set_toast(message)
    window.setTimeout(() => set_toast(null), 1800)
  }

  const current = models.find((item) => item.id === current_model) ?? models[0]
  const enabled_count = Object.values(policy).filter(Boolean).length
  const config = model_config_query.data?.data.config
  const diagnostic = config?.diagnostic_model
  const judge = config?.judge_model

  return (
    <div className="model-page">
      <div className="model-breadcrumb"><button onClick={() => navigate('/workbench')} type="button">会话工作台</button><span>/</span><strong>模型服务</strong></div>

      <section className="model-page-head">
        <div><div className="model-eyebrow">工作台配置</div><h1>模型服务</h1><p>展示后端当前生效配置。Provider 编辑、凭据管理和连接测试尚未启用。</p></div>
        <div className="model-head-actions"><button className="model-button" disabled onClick={() => show_toast('连接测试能力尚未启用。')} type="button">检查全部连接</button><button className="model-button primary" disabled onClick={() => set_modal_open(true)} type="button">＋ 添加模型服务</button></div>
      </section>

      {model_config_query.isPending && <div className="model-inline-state">正在读取当前生效配置…</div>}
      {model_config_query.isError && <div className="model-inline-state error">暂时无法读取模型配置，请稍后重试。</div>}

      <section className="model-summary">
        <article><small>诊断模型</small><strong>{diagnostic?.model ?? '未配置'}</strong><span>{diagnostic ? `${diagnostic.provider} · ${config?.mode === 'mock' ? 'Mock 模式' : '真实模式'}` : '后端未返回配置'}</span></article>
        <article><small>裁判模型</small><strong>{judge?.model ?? '未配置'}</strong><span>{judge ? judge.provider : '未配置独立裁判模型'}</span></article>
        <article><small>本地偏好</small><strong>{current.name}</strong><span>仅影响当前页面，不改变后端配置</span></article>
        <article><small>Agent 策略</small><strong>{enabled_count} <em>项开启</em></strong><span>仅保存本地 UI 偏好</span></article>
      </section>

      <section className="model-section" id="providers">
        <div className="model-section-head"><div><h2>当前生效配置</h2><p>以下信息来自后端配置读取，不代表已执行连接测试。</p></div><button className="model-link" disabled type="button">模型发现未启用 →</button></div>
        <div className="model-provider-list">{model_config_query.isSuccess && [diagnostic, judge].map((item, index) => <article className="model-provider" key={item?.model ?? `unconfigured-${index}`}><div className="provider-logo provider-gateway">{index === 0 ? 'D' : 'J'}</div><div className="provider-main"><strong>{index === 0 ? '诊断模型' : '裁判模型'}</strong><span>{item ? `${item.provider} · ${item.base_url_host}` : '未配置'}</span><div className="provider-tags"><i>{config?.mode === 'mock' ? 'Mock 模式' : '真实模式'}</i><i>{item?.model ?? '未配置模型'}</i></div></div><div className="provider-meta"><small>配置状态</small><b className={`provider-state ${item?.status === 'configured' ? 'sample' : 'muted'}`}>{item?.status === 'configured' ? '已配置' : '未配置'}</b><span>{item?.status === 'configured' ? '当前生效配置' : '后端没有该模型配置'}</span></div><div className="provider-actions"><button className="model-link" disabled type="button">查看详情</button><button aria-label={`${index === 0 ? '诊断模型' : '裁判模型'} 更多操作`} className="more-button" disabled type="button">···</button></div></article>)}</div>
      </section>

      {model_config_query.isSuccess && <section className="model-section" id="models">
        <div className="model-section-head"><div><h2>本地页面偏好</h2><p>选择仅用于页面展示的本地偏好，不会写入或改变后端生效配置。</p></div><button className="model-link" disabled type="button">刷新模型列表未启用 →</button></div>
        <div className="model-grid">{models.map((item) => <article className={`model-card${current_model === item.id ? ' selected' : ''}`} key={item.id}><div className="model-card-head"><div><strong>{item.name}</strong><small>{item.provider}</small></div>{current_model === item.id && <span className="default-mark">当前偏好</span>}</div><p>{item.description}</p><div className="model-tags">{item.tags.map((tag) => <i key={tag}>{tag}</i>)}</div><button className="model-card-action" onClick={() => { set_current_model(item.id); show_toast(`已将 ${item.name} 设为本地偏好。`) }} type="button">{current_model === item.id ? '当前选择' : '设为当前偏好'}</button></article>)}</div>
      </section>}

      <section className="model-section" id="policy">
        <div className="model-section-head"><div><h2>Agent 调用策略</h2><p>对应当前项目 Coordinator、领域 Agent 和质量保障组件；开关仅保存到本地。</p></div><button className="model-link" onClick={() => { set_policy({ ...default_policy }); show_toast('Agent 策略已恢复默认。') }} type="button">恢复默认 →</button></div>
        <div className="model-policy-layout"><div className="model-card policy-card"><div className="model-card-title"><h3>Agent 与任务路由</h3><p>本页面不改变后端 Coordinator 的真实装配。</p></div>{agent_policies.map((item) => <div className="policy-row" key={item.key}><div><strong>{item.name}</strong><small>{item.description}</small></div><span className="policy-model">{item.model}</span><button aria-label={`${item.name} 策略开关`} aria-pressed={policy[item.key]} className={`policy-toggle${policy[item.key] ? ' on' : ''}`} onClick={() => set_policy((current_policy) => ({ ...current_policy, [item.key]: !current_policy[item.key] }))} type="button"><span /></button></div>)}</div><div className="model-card boundary-card" id="security"><div className="model-card-title"><h3>运行边界</h3><p>模型角色不能绕过 Agent、Tool Gateway 和审批策略。</p></div><ul><li>Coordinator 只负责路由，不直接获得任意服务访问权</li><li>DB / Server / Log Agent 只能调用各自注册的受控 Tool</li><li>Tool 调用进入后端网关，Trace 只展示安全摘要</li><li>Debate、Reflection、Report 只处理结构化诊断结果</li><li>高风险动作仍需提案、审批、白名单执行和验证</li></ul><div className="boundary-note">当前模型页只保存本地 UI 偏好。Provider、Connector、凭据和审批权限不在此处直接修改。</div></div></div>
      </section>

      {modal_open && <div className="model-modal" role="dialog" aria-modal="true" aria-labelledby="model-modal-title"><div className="model-dialog"><div className="model-dialog-head"><div><strong id="model-modal-title">添加模型服务</strong><p>选择 Provider 类型，下一步配置暂不实现。</p></div><button aria-label="关闭" className="more-button" onClick={() => set_modal_open(false)} type="button">×</button></div><div className="provider-options">{providers.map((provider) => <button className={`provider-option${selected_provider === provider.key ? ' selected' : ''}`} key={provider.key} onClick={() => set_selected_provider(provider.key)} type="button"><strong>{provider.name}</strong><span>{provider.key === 'ollama' ? '本地地址 · 自动发现模型' : provider.key === 'gateway' ? '中转站 · 公司网关 · 自建服务' : '示例 Provider · 需要后端接入'}</span></button>)}</div><div className="model-dialog-footer"><button className="model-button" onClick={() => set_modal_open(false)} type="button">取消</button><button className="model-button primary" onClick={() => { set_modal_open(false); show_toast(`已进入 ${providers.find((item) => item.key === selected_provider)?.name ?? 'Provider'} 配置流程。`) }} type="button">继续配置</button></div></div></div>}
      {toast && <div className="model-toast" role="status">{toast}</div>}
    </div>
  )
}
