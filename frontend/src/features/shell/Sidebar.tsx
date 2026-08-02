import type { ReactElement } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

interface SidebarProps {
  collapsed: boolean
  on_collapse: () => void
}

/** 包 1：只呈现侧栏骨架（品牌 / 新建 / 历史占位 / 用户卡）。
 *  真实会话列表在包 3（左栏）接入 API；此处先不触发请求，避免破坏既有会话链路测试。 */
export function Sidebar({ collapsed, on_collapse }: SidebarProps): ReactElement {
  const navigate = useNavigate()
  const location = useLocation()
  const in_session = location.pathname.includes('/sessions/')

  return (
    <aside aria-label="会话导航" className={`sidebar${collapsed ? ' collapsed' : ''}`}>
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

      <div className="history-heading">
        <span>最近会话</span>
      </div>
      <nav className="history-list">
        {!in_session && (
          <span className="history-item" style={{ color: 'var(--text-muted)' }}>
            会话列表将在下一工作包接入
          </span>
        )}
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
