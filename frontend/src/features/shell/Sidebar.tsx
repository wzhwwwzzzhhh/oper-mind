import { useQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { list_sessions_query } from '../../api/v1/queries'
import { read_items, resource_optional_string, resource_string } from '../workbench/resource-readers'
import { Icon } from './Icon'

interface SidebarProps {
  collapsed: boolean
  on_collapse: () => void
}

/** 第二栏（会话模式）：品牌 + 新建会话 + 最近会话列表（接真实 API）；运维中心走最左侧全局导航。 */
export function Sidebar({ collapsed, on_collapse }: SidebarProps): ReactElement {
  const navigate = useNavigate()
  const location = useLocation()
  const current_session_id = location.pathname.match(/\/sessions\/([^/]+)/)?.[1]

  const sessions_query = useQuery({ ...list_sessions_query({ limit: 20, status: 'active' }) })
  const sessions = sessions_query.data ? read_items(sessions_query.data.data) : []

  return (
    <aside aria-label="会话导航" className={`second chat-side${collapsed ? ' collapsed' : ''}`}>
      <div className="brand-row">
        <a aria-label="OperMind 首页" className="brand" href="/workbench">
          <span className="brand-mark">O</span>
          <span className="brand-copy">
            OperMind
            <small>DEVOPS COPILOT</small>
          </span>
        </a>
        <button aria-label="收起侧栏" className="icon-btn" id="collapse-btn" onClick={on_collapse} type="button">
          <Icon className="icon" name="chevron-left" size={15} />
        </button>
      </div>

      <button className="new-chat" onClick={() => navigate('/workbench')} type="button">
        <span className="plus">＋</span>
        <span className="new-chat-label">新建会话</span>
      </button>

      <div className="history-heading">
        <span>最近会话</span>
      </div>
      <nav className="history-list">
        {sessions_query.isPending && (
          <span className="history-item" style={{ color: 'var(--text-muted)' }}>正在加载会话…</span>
        )}
        {sessions_query.isSuccess && sessions.length === 0 && (
          <span className="history-item" style={{ color: 'var(--text-muted)' }}>还没有会话</span>
        )}
        {sessions_query.isError && (
          <span className="history-item" style={{ color: 'var(--text-muted)' }}>会话列表暂不可读</span>
        )}
        {sessions.map((session) => {
          const session_id = resource_optional_string(session, 'id')
          const title = resource_string(session, 'title', '未命名会话')
          const active = session_id != null && session_id === current_session_id
          return (
            <button
              aria-current={active ? 'true' : undefined}
              className={`history-item${active ? ' active' : ''}`}
              disabled={!session_id}
              key={session_id ?? title}
              onClick={() => session_id && navigate(`/workbench/sessions/${encodeURIComponent(session_id)}`)}
              type="button"
            >
              {title}
            </button>
          )
        })}
      </nav>
      <button className="approvals-entry" onClick={() => navigate('/workbench/approvals')} type="button">
        <Icon className="icon" name="stack" size={15} />
        <span>待审批</span>
      </button>
    </aside>
  )
}
