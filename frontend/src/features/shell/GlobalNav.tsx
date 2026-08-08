import type { ReactElement } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

/** 最左 62px 全局图标导航：会话 / 服务中心 / 监控 / 文档 / 模型。 */
export function GlobalNav(): ReactElement {
  const navigate = useNavigate()
  const location = useLocation()
  const on_services = location.pathname.startsWith('/services')
  const on_models = location.pathname.startsWith('/models')
  const on_knowledge = location.pathname.startsWith('/knowledge')

  const items = [
    { key: 'chat', icon: '⌂', label: '会话工作台', active: !on_services && !on_models && !on_knowledge },
    { key: 'services', icon: '◫', label: '服务中心', active: on_services },
    { key: 'monitor', icon: '◌', label: '服务监控', active: false },
    { key: 'docs', icon: '▤', label: '文档知识库', active: on_knowledge },
    { key: 'models', icon: '✦', label: '模型设置', active: on_models },
  ]

  const go = (key: string): void => {
    if (key === 'chat') navigate('/workbench')
    else if (key === 'services') navigate('/services')
    else if (key === 'docs') navigate('/knowledge')
    else if (key === 'models') navigate('/models')
  }

  return (
    <aside aria-label="全局导航" className="global">
      <a aria-label="OperMind" className="logo" href="/workbench">O</a>
      <nav className="global-nav">
        {items.map((item) => (
          <button
            aria-label={item.label}
            className={`global-item${item.active ? ' active' : ''}`}
            key={item.key}
            onClick={() => go(item.key)}
            type="button"
          >
            {item.icon}
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="global-bottom">
        <div className="global-avatar">W</div>
      </div>
    </aside>
  )
}
