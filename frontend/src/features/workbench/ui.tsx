import type { CSSProperties, ReactElement, ReactNode } from 'react'
import { useState } from 'react'

/* P3-PKG7：自绘 UI 原语，替代工作台曾依赖的第三方 UI 库组件。
   仅覆盖工作台仍在使用的最小集合；样式类前缀 ui-，语义与既有 UI 库对齐但不依赖任何 UI 库。 */

type UiAlertType = 'info' | 'success' | 'warning' | 'error'

const ALERT_ICONS: Record<UiAlertType, string> = {
  info: 'ℹ',
  success: '✓',
  warning: '⚠',
  error: '✕',
}

interface UiAlertProps {
  action?: ReactNode
  className?: string
  description?: ReactNode
  showIcon?: boolean
  title?: ReactNode
  type: UiAlertType
}

/** 提醒条：标题 + 说明 + 可选操作，视觉对齐原 UI 库的 Alert。 */
export function UiAlert({ action, className, description, showIcon, title, type }: UiAlertProps): ReactElement {
  return (
    <div className={`ui-alert ui-alert--${type}${className ? ` ${className}` : ''}`} role={type === 'error' ? 'alert' : undefined}>
      {showIcon && <span aria-hidden="true" className="ui-alert__icon">{ALERT_ICONS[type]}</span>}
      <div className="ui-alert__content">
        {title != null && <div className="ui-alert__title">{title}</div>}
        {description != null && <div className="ui-alert__desc">{description}</div>}
      </div>
      {action != null && <div className="ui-alert__action">{action}</div>}
    </div>
  )
}

type UiButtonType = 'default' | 'primary' | 'link'

interface UiButtonProps {
  children?: ReactNode
  className?: string
  danger?: boolean
  disabled?: boolean
  loading?: boolean
  onClick?: () => void
  type?: UiButtonType
}

/** 按钮：primary / danger / link 变体 + 加载态，视觉对齐原 UI 库的 Button。 */
export function UiButton({ children, className, danger, disabled, loading, onClick, type = 'default' }: UiButtonProps): ReactElement {
  const variant = type === 'primary' ? ' primary' : type === 'link' ? ' link' : ''
  const danger_class = danger ? ' danger' : ''
  return (
    <button
      className={`ui-btn${variant}${danger_class}${className ? ` ${className}` : ''}`}
      disabled={disabled || loading}
      onClick={onClick}
      type="button"
    >
      {loading && <span aria-hidden="true" className="ui-btn__spinner" />}
      {children}
    </button>
  )
}

type UiTagColor = 'green' | 'red' | 'blue' | 'cyan' | 'gold' | 'orange'

interface UiTagProps {
  children: ReactNode
  color?: UiTagColor
}

/** 标签：可选语义色，视觉对齐原 UI 库的 Tag。 */
export function UiTag({ children, color }: UiTagProps): ReactElement {
  return <span className={`ui-tag${color ? ` ui-tag--${color}` : ''}`}>{children}</span>
}

interface UiSpaceProps {
  children: ReactNode
  className?: string
  direction?: 'horizontal' | 'vertical'
  size?: number | 'middle' | 'small'
  style?: CSSProperties
  wrap?: boolean
}

const SPACE_GAP: Record<'middle' | 'small', number> = { middle: 14, small: 8 }

/** 间距容器：行/列布局 + 换行，视觉对齐原 UI 库的 Space。 */
export function UiSpace({ children, className, direction = 'horizontal', size = 'small', style, wrap }: UiSpaceProps): ReactElement {
  const gap = typeof size === 'number' ? size : SPACE_GAP[size]
  return (
    <div
      className={`ui-space${direction === 'vertical' ? ' ui-space--vertical' : ''}${wrap ? ' ui-space--wrap' : ''}${className ? ` ${className}` : ''}`}
      style={{ gap, ...style }}
    >
      {children}
    </div>
  )
}

interface UiCardProps {
  children: ReactNode
  title?: ReactNode
}

/** 卡片：标题 + 主体，视觉对齐原 UI 库的 Card（内嵌小卡）。 */
export function UiCard({ children, title }: UiCardProps): ReactElement {
  return (
    <section className="ui-card">
      {title != null && <header className="ui-card__head">{title}</header>}
      <div className="ui-card__body">{children}</div>
    </section>
  )
}

interface UiTitleProps {
  children: ReactNode
  className?: string
  id?: string
  level: 2 | 5
}

/** 标题：按 level 渲染 h2/h5，视觉对齐原 UI 库的 Typography.Title。 */
export function UiTitle({ children, className, id, level }: UiTitleProps): ReactElement {
  const Heading = level === 2 ? 'h2' : 'h5'
  return <Heading className={`ui-title ui-title--${level}${className ? ` ${className}` : ''}`} id={id}>{children}</Heading>
}

interface UiTextProps {
  children?: ReactNode
  className?: string
  strong?: boolean
}

/** 文本：可选加粗，视觉对齐原 UI 库的 Typography.Text。 */
export function UiText({ children, className, strong }: UiTextProps): ReactElement {
  return <span className={`ui-text${strong ? ' ui-text--strong' : ''}${className ? ` ${className}` : ''}`}>{children}</span>
}

interface UiParagraphProps {
  children?: ReactNode
  className?: string
}

/** 段落：视觉对齐原 UI 库的 Typography.Paragraph。 */
export function UiParagraph({ children, className }: UiParagraphProps): ReactElement {
  return <p className={`ui-paragraph${className ? ` ${className}` : ''}`}>{children}</p>
}

interface UiDescriptionsItemProps {
  children?: ReactNode
  label: string
}

/** 描述项：字段标签 + 值。 */
export function UiDescriptionsItem({ children, label }: UiDescriptionsItemProps): ReactElement {
  return (
    <div className="ui-descriptions__row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  )
}

interface UiDescriptionsProps {
  children: ReactNode
  title?: ReactNode
}

/** 描述列表：单列表格，视觉对齐原 UI 库的 Descriptions。 */
export function UiDescriptions({ children, title }: UiDescriptionsProps): ReactElement {
  return (
    <section className="ui-descriptions">
      {title != null && <h4 className="ui-descriptions__title">{title}</h4>}
      <dl className="ui-descriptions__list">{children}</dl>
    </section>
  )
}

interface UiListProps<T> {
  dataSource: readonly T[]
  renderItem: (item: T) => ReactNode
}

/** 列表：dataSource + 渲染函数，视觉对齐原 UI 库的 List（小号）。 */
export function UiList<T>({ dataSource, renderItem }: UiListProps<T>): ReactElement {
  return (
    <ul className="ui-list">
      {dataSource.map((item, index) => (
        <li className="ui-list__item" key={index}>{renderItem(item)}</li>
      ))}
    </ul>
  )
}

interface UiModalProps {
  cancelText: string
  children: ReactNode
  confirmLoading?: boolean
  okButtonProps?: { danger?: boolean }
  okText: string
  onCancel: () => void
  onOk: () => void
  open: boolean
  title: ReactNode
}

/** 确认弹窗：遮罩 + 对话框 + 取消/确认，视觉对齐原 UI 库的 Modal。 */
export function UiModal({ cancelText, children, confirmLoading, okButtonProps, okText, onCancel, onOk, open, title }: UiModalProps): ReactElement {
  if (!open) return <div className="ui-modal" hidden />
  return (
    <div aria-modal="true" className="ui-modal" role="dialog">
      <div className="ui-modal__dialog" onClick={(event) => event.stopPropagation()}>
        <header className="ui-modal__head">{title}</header>
        <div className="ui-modal__body">{children}</div>
        <footer className="ui-modal__footer">
          <UiButton onClick={onCancel}>{cancelText}</UiButton>
          <UiButton danger={okButtonProps?.danger} loading={confirmLoading} onClick={onOk} type="primary">{okText}</UiButton>
        </footer>
      </div>
    </div>
  )
}

interface UiSpinProps {
  label: string
}

/** 加载态：旋转指示器，视觉对齐原 UI 库的 Spin（小号）。 */
export function UiSpin({ label }: UiSpinProps): ReactElement {
  return <span className="ui-spin" role="status" aria-label={label} />
}

interface UiSkeletonProps {
  active?: boolean
  paragraph?: { rows: number }
  title?: boolean
}

/** 骨架屏：标题 + 若干占位行，视觉对齐原 UI 库的 Skeleton。 */
export function UiSkeleton({ active, paragraph, title }: UiSkeletonProps): ReactElement {
  const rows = paragraph?.rows ?? 3
  return (
    <div className={`ui-skeleton${active ? ' ui-skeleton--active' : ''}`}>
      {title && <span className="ui-skeleton__line ui-skeleton__line--title" />}
      {Array.from({ length: rows }, (_, index) => <span className="ui-skeleton__line" key={index} />)}
    </div>
  )
}

interface UiCollapseItem {
  children: ReactNode
  key: string
  label: ReactNode
}

interface UiCollapseProps {
  className?: string
  items: UiCollapseItem[]
}

/** 折叠面板：默认折叠，点击标题展开，视觉对齐原 UI 库的 Collapse。 */
export function UiCollapse({ className, items }: UiCollapseProps): ReactElement {
  const [open_keys, set_open_keys] = useState<Set<string>>(new Set())
  return (
    <div className={`ui-collapse${className ? ` ${className}` : ''}`}>
      {items.map((item) => {
        const open = open_keys.has(item.key)
        return (
          <div className={`ui-collapse__item${open ? ' open' : ''}`} key={item.key}>
            <button
              aria-expanded={open}
              className="ui-collapse__head"
              onClick={() => set_open_keys((current) => {
                const next = new Set(current)
                if (next.has(item.key)) next.delete(item.key)
                else next.add(item.key)
                return next
              })}
              type="button"
            >
              <span className="ui-collapse__label">{item.label}</span>
              <span aria-hidden="true" className="ui-collapse__toggle">⌄</span>
            </button>
            {open && <div className="ui-collapse__body">{item.children}</div>}
          </div>
        )
      })}
    </div>
  )
}
