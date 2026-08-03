import type { ReactElement } from 'react'

interface TopBarProps {
  on_theme: () => void
  on_share: () => void
}

export function TopBar({ on_theme, on_share }: TopBarProps): ReactElement {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="model-select" type="button">
          OperMind-Reasoner
        </button>
        <span className="online-dot" title="服务在线" />
      </div>
      <div className="topbar-right">
        <button className="top-action theme-button" onClick={on_theme} type="button">
          ◐ <span>主题</span>
        </button>
        <button className="top-action" onClick={on_share} type="button">
          ⌁ <span>分享</span>
        </button>
      </div>
    </header>
  )
}
