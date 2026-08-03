import { useQuery } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { list_sessions_query } from '../../api/v1/queries'
import { read_items, resource_optional_string, resource_string } from '../workbench/resource-readers'

interface SidebarProps {
  collapsed: boolean
  on_collapse: () => void
}

/** 第二栏（会话模式）：品牌 + 新建会话 + 运维中心入口卡 + 最近会话列表（接真实 API）。 */
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
          ‹
        </button>
      </div>

      <button className="new-chat" onClick={() => navigate('/workbench')} type="button">
        <span className="plus">＋</span>
        <span className="new-chat-label">新建会话</span>
        <span className="new-chat-shortcut">Ctrl K</span>
      </button>

      {/* 运维中心入口 */}
      <button className="ops-entry" onClick={() => navigate('/services')} type="button">
        <span className="ops-icon">◫</span>
        <span className="ops-copy">
          <strong>运维中心</strong>
          <span>服务接入 · 监控 · 调查</span>
        </span>
        <span className="ops-arrow">›</span>
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

      <div className="sidebar-footer">
        <div className="user-card">
          <span className="avatar">W</span>
          <span className="user-copy">
            <strong>王志海</strong>
            <span>研发运维团队</span>
          </span>
        </div>
      </div>
    </aside>
  )
}
