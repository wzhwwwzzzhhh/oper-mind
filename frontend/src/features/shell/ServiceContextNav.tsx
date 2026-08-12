import type { ReactElement } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { useQuery } from '@tanstack/react-query'
import { list_services_query } from '../../api/v1/queries'
import { read_items } from '../workbench/resource-readers'
import { Icon } from './Icon'

/** 第二栏上下文导航：服务中心、服务监控、模型服务和文档知识库共用运维模式壳。 */
export function ServiceContextNav(): ReactElement {
  const navigate = useNavigate()
  const location = useLocation()
  const is_models = location.pathname.startsWith('/models')
  const is_monitor = location.pathname.startsWith('/monitor')
  const is_knowledge = location.pathname.startsWith('/knowledge')
  const is_audit = location.pathname.startsWith('/audit')
  const services_query = useQuery({
    ...list_services_query(),
    enabled: !is_models && !is_monitor && !is_knowledge && !is_audit,
  })
  const service_count = services_query.data ? read_items(services_query.data.data).length : 0

  if (is_knowledge) {
    return (
      <aside aria-label="文档知识库导航" className="second svc-context knowledge-context">
        <div className="svc-context-head">
          <div className="svc-context-mark"><Icon name="book" size={15} /></div>
          <div>
            <strong>文档知识库</strong>
            <span>受管知识目录</span>
          </div>
        </div>
        <p className="svc-label">知识库</p>
        <nav className="svc-nav">
          <button className="svc-link active" onClick={() => navigate('/knowledge')} type="button">
            <i><Icon name="book" size={13} /></i>
            文档浏览与检索
          </button>
        </nav>
        <div className="svc-divider" />
        <div className="context-card">
          <small>数据来源</small>
          <strong>受管知识目录 · 只读</strong>
          <span>目录由 OPERMIND_KNOWLEDGE_DIR 配置；未配置时如实显示未启用。</span>
          <b>只读浏览</b>
        </div>
        <div className="svc-bottom">
          <strong>当前访问边界</strong>
          只读受管目录 · 凭据文件排除
        </div>
      </aside>
    )
  }

  if (is_models) {
    return (
      <aside aria-label="模型服务导航" className="second svc-context model-context">
        <div className="svc-context-head">
          <div className="svc-context-mark"><Icon name="spark" size={15} /></div>
          <div>
            <strong>模型服务</strong>
            <span>Provider 与调用策略</span>
          </div>
        </div>
        <p className="svc-label">模型设置</p>
        <nav className="svc-nav">
          <button className="svc-link active" onClick={() => navigate('/models')} type="button">
            <i><Icon name="spark" size={13} /></i>
            模型服务
          </button>
        </nav>
        <div className="svc-divider" />
        <div className="context-card">
          <small>说明</small>
          <strong>模型 Provider 管理</strong>
          <span>可在此添加、验证并切换诊断模型。配置项由后端持久化，不依赖浏览器本地存储。</span>
        </div>
        <div className="svc-bottom">
          <strong>当前页面边界</strong>
          Provider CRUD · 连接验证
        </div>
      </aside>
    )
  }

  return (
    <aside aria-label="服务中心导航" className="second svc-context">
      <div className="svc-context-head">
        <div className="svc-context-mark"><Icon name="database" size={15} /></div>
        <div>
          <strong>服务中心</strong>
          <span>已接入服务目录</span>
        </div>
      </div>
      <p className="svc-label">服务中心</p>
      <nav className="svc-nav">
        <button className={`svc-link${!is_monitor && !is_audit ? ' active' : ''}`} onClick={() => navigate('/services')} type="button">
          <i><Icon name="stack" size={13} /></i>
          已接入服务
          {service_count > 0 && <span className="svc-count">{service_count}</span>}
        </button>
        <button className={`svc-link${is_monitor ? ' active' : ''}`} onClick={() => navigate('/monitor')} type="button">
          <i><Icon name="pulse" size={13} /></i>
          服务监控
          <span className="svc-link-note">定时采样</span>
        </button>
        <button className={`svc-link${is_audit ? ' active' : ''}`} onClick={() => navigate('/audit')} type="button">
          <i><Icon name="shield" size={13} /></i>
          审计操作记录
        </button>
      </nav>
      <div className="svc-divider" />
      <div className="svc-bottom">
        <strong>当前访问策略</strong>
        默认只读 · 高风险动作需人工审批
      </div>
    </aside>
  )
}
