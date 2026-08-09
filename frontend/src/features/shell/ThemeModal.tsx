import type { ReactElement } from 'react'

import { THEMES, useThemeStore, type ThemeKey } from '../../stores/use-theme-store'
import { Icon } from './Icon'

interface ThemeModalProps {
  on_close: () => void
  open: boolean
}

/** 主题选择弹窗：3 套主题，按对比度策略区分而不是色相轮换。 */
export function ThemeModal({ on_close, open }: ThemeModalProps): ReactElement {
  const theme = useThemeStore((state) => state.theme)
  const set_theme = useThemeStore((state) => state.set_theme)

  return (
    <div aria-modal="true" className={`theme-modal${open ? ' open' : ''}`} onClick={on_close} role="dialog">
      <div className="theme-dialog" onClick={(event) => event.stopPropagation()}>
        <div className="theme-dialog-head">
          <div>
            <strong>选择主题</strong>
            <span>只改变视觉风格，不影响会话内容和交互。</span>
          </div>
          <button aria-label="关闭主题选择" className="icon-btn" onClick={on_close} type="button">
            <Icon name="x" size={14} />
          </button>
        </div>
        <div className="theme-grid">
          {THEMES.map((item) => {
            const selected = theme === item.key
            return (
              <button
                className={`theme-option${selected ? ' selected' : ''}`}
                key={item.key}
                onClick={() => set_theme(item.key as ThemeKey)}
                type="button"
              >
                <div className={`theme-preview ${item.key}`}>
                  <i className="preview-dot" />
                </div>
                <div className="theme-copy">
                  <strong>{item.name}</strong>
                  <span>{item.desc}</span>
                  {selected && (
                    <span className="theme-check">
                      <Icon name="check" size={11} />
                      当前主题
                    </span>
                  )}
                </div>
              </button>
            )
          })}
        </div>
        <div className="theme-footer">主题偏好会保存在当前浏览器中</div>
      </div>
    </div>
  )
}
