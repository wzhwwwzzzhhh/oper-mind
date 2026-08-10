import type { ReactElement } from 'react'

import { Icon } from './Icon'

interface TopBarProps {
  on_theme: () => void
  on_share: () => void
  /** 当前页面标题，留空时不渲染。 */
  title?: string
}

/** 主区顶栏：只保留真实已连接操作（主题切换、分享通知）。 */
export function TopBar({ on_theme, on_share, title }: TopBarProps): ReactElement {
  return (
    <header className="topbar">
      <div className="topbar-left">
        {title && <span className="topbar-title">{title}</span>}
      </div>
      <div className="topbar-right">
        <button aria-label="切换主题" className="top-action theme-button" onClick={on_theme} title="切换主题" type="button">
          <Icon name="contrast" size={15} />
          <span>主题</span>
        </button>
        <button aria-label="分享" className="top-action" onClick={on_share} title="分享" type="button">
          <Icon name="link" size={15} />
          <span>分享</span>
        </button>
      </div>
    </header>
  )
}
