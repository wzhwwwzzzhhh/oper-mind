import type { ReactElement } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

import { Icon, type IconName } from './Icon'

interface NavItem {
  key: string
  icon: IconName
  label: string
  active: boolean
  navigate_to: string
}

/** 最左 62px 深色图标轨：会话 / 服务中心 / 文档 / 模型。
    这里只放正式模块（见 docs/产品定义.md 第 4 节模块边界表）。
    服务监控是服务中心名下的子页，入口在第二栏 ServiceContextNav，不在这条轨上重复一次。 */
export function GlobalNav(): ReactElement {
  const navigate = useNavigate()
  const location = useLocation()
  const on_services = location.pathname.startsWith('/services')
  const on_models = location.pathname.startsWith('/models')
  const on_monitor = location.pathname.startsWith('/monitor')
  const on_knowledge = location.pathname.startsWith('/knowledge')

  const items: NavItem[] = [
    { key: 'chat',     icon: 'message',  label: '会话工作台', active: !on_services && !on_models && !on_monitor && !on_knowledge, navigate_to: '/workbench' },
    // 在 /monitor 上点亮服务中心：监控是它的子页，否则整条轨会没有一颗是亮的。
    { key: 'services', icon: 'database', label: '服务中心',   active: on_services || on_monitor, navigate_to: '/services'  },
    { key: 'docs',     icon: 'book',     label: '文档知识库', active: on_knowledge, navigate_to: '/knowledge' },
    { key: 'models',   icon: 'spark',    label: '模型设置',   active: on_models,    navigate_to: '/models'    },
  ]

  return (
    <aside aria-label="全局导航" className="global">
      <a aria-label="OperMind" className="logo" href="/workbench">O</a>
      <nav className="global-nav">
        {items.map((item) => (
          <button
            aria-label={item.label}
            className={`global-item${item.active ? ' active' : ''}`}
            key={item.key}
            onClick={() => navigate(item.navigate_to)}
            type="button"
          >
            <Icon name={item.icon} size={20} />
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="global-bottom" />
    </aside>
  )
}
