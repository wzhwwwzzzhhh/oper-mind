import { useLayoutEffect, useRef, type ReactElement } from 'react'

import { Icon } from './Icon'

interface ComposerProps {
  disabled?: boolean
  onSubmit: (value: string) => void
  placeholder?: string
  /** 受控值；父组件负责维护（含恢复/禁用语义）。 */
  value: string
  onChange?: (value: string) => void
}

/** 输入框自动增高上限（px）：超过后内部滚动，避免输入区吃掉整屏。 */
const MAX_TEXTAREA_HEIGHT = 320

export function Composer({ disabled, onSubmit, placeholder, value, onChange }: ComposerProps): ReactElement {
  const ready = value.trim().length > 0
  const textarea_ref = useRef<HTMLTextAreaElement>(null)

  // 随内容自动增高：每次值变化后按 scrollHeight 重算，超过上限才交给内部滚动。
  useLayoutEffect(() => {
    const node = textarea_ref.current
    if (node == null) return
    node.style.height = 'auto'
    const next_height = Math.min(node.scrollHeight, MAX_TEXTAREA_HEIGHT)
    node.style.height = `${next_height}px`
    node.style.overflowY = node.scrollHeight > MAX_TEXTAREA_HEIGHT ? 'auto' : 'hidden'
  }, [value])

  const submit = (): void => {
    const text = value.trim()
    if (!text || disabled) return
    onSubmit(text)
  }

  return (
    <div className="composer-wrap">
      <div className="composer-area">
        <div className="composer">
          <textarea
            aria-label="调查问题"
            disabled={disabled}
            onChange={(event) => onChange?.(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                submit()
              }
            }}
            placeholder={placeholder ?? '给 OperMind 发送消息…'}
            ref={textarea_ref}
            rows={2}
            value={value}
          />
          <div className="composer-tools">
            <div className="tool-group">
              <span className="context-strip">
                <Icon className="context-strip__icon" name="shield" size={13} />
                <span>默认只读调查</span>
              </span>
            </div>
            <button aria-label="发送" className={`send-btn${ready ? ' ready' : ''}`} disabled={disabled} onClick={submit} type="button">
              <Icon name="send" size={16} />
            </button>
          </div>
        </div>
        <div className="disclaimer">OperMind 可能会犯错，请核验关键事实。所有外部服务访问均需经过受控连接器。</div>
      </div>
    </div>
  )
}
