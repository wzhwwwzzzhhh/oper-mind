import type { ReactElement } from 'react'
import { useState } from 'react'

interface ComposerProps {
  disabled?: boolean
  onSubmit: (value: string) => void
  placeholder?: string
  initial?: string
}

export function Composer({ disabled, onSubmit, placeholder, initial }: ComposerProps): ReactElement {
  const [value, set_value] = useState(initial ?? '')
  const ready = value.trim().length > 0

  const submit = (): void => {
    const text = value.trim()
    if (!text || disabled) return
    onSubmit(text)
    set_value('')
  }

  return (
    <div className="composer-wrap">
      <div className="composer-area">
        <div className="composer">
          <textarea
            aria-label="调查问题"
            disabled={disabled}
            onChange={(event) => set_value(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                submit()
              }
            }}
            placeholder={placeholder ?? '给 OperMind 发送消息…'}
            rows={1}
            value={value}
          />
          <div className="composer-tools">
            <div className="tool-group">
              <button aria-label="安全策略" className="composer-btn" type="button">
                ◌
              </button>
              <span className="context-strip">
                <span className="context-chip">PostgreSQL</span>
                <span className="context-chip">只读</span>
              </span>
            </div>
            <button aria-label="发送" className={`send-btn${ready ? ' ready' : ''}`} disabled={disabled} onClick={submit} type="button">
              ↑
            </button>
          </div>
        </div>
        <div className="disclaimer">OperMind 可能会犯错，请核验关键事实。所有外部服务访问均需经过受控连接器。</div>
      </div>
    </div>
  )
}
