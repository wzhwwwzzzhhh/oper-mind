import type { ReactElement } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { useQuery } from '@tanstack/react-query'
import { list_services_query } from '../../api/v1/queries'
import { read_items } from '../workbench/resource-readers'

function jump_to(navigate: (to: string) => void, section: string): void {
  navigate(`/models#${section}`)
  window.setTimeout(() => document.getElementById(section)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0)
}

/** 第二栏上下文导航：服务中心、服务监控和模型服务共用运维模式壳。 */
export function ServiceContextNav(): ReactElement {
  const navigate = useNavigate()
  const location = useLocation()
  const is_models = location.pathname.startsWith('/models')
  const is_monitor = location.pathname.startsWith('/monitor')
  const services_query = useQuery({ ...list_services_query(), enabled: !is_models && !is_monitor })
  const service_count = services_query.data ? read_items(services_query.data.data).length : 0

  if (is_models) {
    return (
      <aside aria-label="模型服务导航" className="second svc-context model-context">
        <div className="svc-context-head">
          <div className="svc-context-mark">✦</div>
          <div><strong>模型服务</strong><span>Provider 与调用策略</span></div>
        </div>
        <p className="svc-label">模型设置</p>
        <nav className="svc-nav">
          <button className="svc-link active" onClick={() => jump_to(navigate, 'providers')} type="button"><i>⌘</i>模型服务</button>
          <button className="svc-link" onClick={() => jump_to(navigate, 'models')} type="button"><i>✦</i>可用模型</button>
          <button className="svc-link" onClick={() => jump_to(navigate, 'policy')} type="button"><i>◈</i>默认策略</button>
          <button className="svc-link" onClick={() => jump_to(navigate, 'security')} type="button"><i>◇</i>安全与权限</button>
        </nav>
        <div className="svc-divider" />
        <div className="model-context-card"><small>当前本地偏好</small><strong>DeepSeek Reasoner</strong><span>模型状态需由后端接口确认</span><b>未连接验证</b></div>
        <div className="svc-bottom"><strong>当前页面边界</strong>静态展示 · localStorage 本地策略</div>
      </aside>
    )
  }

  return (
    <aside aria-label="服务中心导航" className="second svc-context">
      <div className="svc-context-head">
        <div className="svc-context-mark">◫</div>
        <div><strong>服务中心</strong><span>platform-team</span></div>
      </div>
      <p className="svc-label">服务中心</p>
      <nav className="svc-nav">
        <button className={`svc-link${!is_monitor ? ' active' : ''}`} onClick={() => navigate('/services')} type="button"><i>⌂</i>概览</button>
        <button className={`svc-link${!is_monitor ? ' active' : ''}`} onClick={() => navigate('/services')} type="button"><i>◫</i>已接入服务<span className="svc-count">{service_count}</span></button>
        <button className={`svc-link${is_monitor ? ' active' : ''}`} onClick={() => navigate('/monitor')} type="button"><i>◌</i>服务监控<span>定时采样</span></button>
      </nav>
      <div className="svc-divider" />
      <p className="svc-label">快捷操作</p>
      <button className="svc-action" type="button"><i>＋</i>接入新服务</button>
      <div className="svc-bottom"><strong>当前访问策略</strong>默认只读 · 高风险动作需人工审批</div>
    </aside>
  )
}
