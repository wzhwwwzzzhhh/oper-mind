import type { ReactElement } from 'react'
import { useNavigate } from 'react-router-dom'

import { useQuery } from '@tanstack/react-query'
import { list_services_query } from '../../api/v1/queries'
import { read_items } from '../workbench/resource-readers'

/** 第二栏（运维模式）：服务中心上下文导航。 */
export function ServiceContextNav(): ReactElement {
  const navigate = useNavigate()
  const services_query = useQuery({ ...list_services_query() })
  const service_count = services_query.data ? read_items(services_query.data.data).length : 0

  return (
    <aside aria-label="服务中心导航" className="second svc-context">
      <div className="svc-context-head">
        <div className="svc-context-mark">◫</div>
        <div>
          <strong>服务中心</strong>
          <span>platform-team</span>
        </div>
      </div>
      <p className="svc-label">服务中心</p>
      <nav className="svc-nav">
        <button className="svc-link active" onClick={() => navigate('/services')} type="button">
          <i>⌂</i>概览
        </button>
        <button className="svc-link" onClick={() => navigate('/services')} type="button">
          <i>◫</i>已接入服务<span className="svc-count">{service_count}</span>
        </button>
      </nav>
      <div className="svc-divider" />
      <p className="svc-label">快捷操作</p>
      <button className="svc-action" type="button"><i>＋</i>接入新服务</button>
      <div className="svc-bottom">
        <strong>当前访问策略</strong>
        默认只读 · 高风险动作需人工审批
      </div>
    </aside>
  )
}
