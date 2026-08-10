import type { ReactElement } from 'react'

/** 线性图标名；统一 24 网格、1.6 描边、继承 currentColor。 */
export type IconName =
  | 'alert'
  | 'book'
  | 'check'
  | 'chevron-down'
  | 'chevron-left'
  | 'chevron-right'
  | 'clock'
  | 'contrast'
  | 'database'
  | 'link'
  | 'message'
  | 'minus'
  | 'plus'
  | 'pulse'
  | 'refresh'
  | 'search'
  | 'send'
  | 'shield'
  | 'spark'
  | 'stack'
  | 'x'

const PATHS: Readonly<Record<IconName, ReactElement>> = {
  alert: <><path d="M12 4.5 3 19.5h18L12 4.5Z" /><path d="M12 10v4" /><path d="M12 17h.01" /></>,
  book: <><path d="M5 4.5h9a3 3 0 0 1 3 3v12H8a3 3 0 0 1-3-3v-12Z" /><path d="M17 19.5h2v-13" /><path d="M8.5 8.5h5" /><path d="M8.5 12h5" /></>,
  check: <path d="m4.5 12.5 5 5 10-11" />,
  'chevron-down': <path d="m5.5 9.5 6.5 7 6.5-7" />,
  'chevron-left': <path d="m14.5 5.5-7 6.5 7 6.5" />,
  'chevron-right': <path d="m9.5 5.5 7 6.5-7 6.5" />,
  clock: <><circle cx="12" cy="12" r="8" /><path d="M12 7.5V12l3.5 2" /></>,
  contrast: <><circle cx="12" cy="12" r="8.2" /><path d="M12 3.8v16.4a8.2 8.2 0 0 0 0-16.4Z" fill="currentColor" stroke="none" /></>,
  database: <><ellipse cx="12" cy="6.5" rx="7" ry="2.8" /><path d="M5 6.5v11c0 1.55 3.13 2.8 7 2.8s7-1.25 7-2.8v-11" /><path d="M5 12c0 1.55 3.13 2.8 7 2.8s7-1.25 7-2.8" /></>,
  link: <><path d="M10 13.8a3.6 3.6 0 0 0 5.1 0l2.7-2.7a3.6 3.6 0 0 0-5.1-5.1L11.4 7.3" /><path d="M14 10.2a3.6 3.6 0 0 0-5.1 0l-2.7 2.7a3.6 3.6 0 0 0 5.1 5.1l1.3-1.3" /></>,
  message: <path d="M4.5 6a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9.5L5.5 20v-4h-1Z" />,
  /** 缺数据标记；与页面正文里的“—”是同一个意思。 */
  minus: <path d="M5.5 12h13" />,
  plus: <><path d="M12 5.5v13" /><path d="M5.5 12h13" /></>,
  pulse: <path d="M3.5 12.5h3.2l2.1-5.5 3.3 10 2.3-6.2 1.6 2.7h4.5" />,
  refresh: <><path d="M19.5 12a7.5 7.5 0 0 1-13.2 4.8" /><path d="M4.5 12a7.5 7.5 0 0 1 13.2-4.8" /><path d="M17.5 3.8v3.6h-3.6" /><path d="M6.5 20.2v-3.6h3.6" /></>,
  search: <><circle cx="11" cy="11" r="6.2" /><path d="m15.6 15.6 4 4" /></>,
  send: <><path d="M12 19V5.5" /><path d="m6 11.5 6-6 6 6" /></>,
  shield: <><path d="M12 3.8 5 6.4v5.3c0 4.2 2.9 7.4 7 8.5 4.1-1.1 7-4.3 7-8.5V6.4L12 3.8Z" /><path d="m9 12 2.3 2.3L15.5 10" /></>,
  spark: <><path d="M12 3.5 13.7 9l5.8 1.7-5.8 1.7L12 18l-1.7-5.6L4.5 10.7 10.3 9 12 3.5Z" /><path d="M18.5 16.5 19 18l1.5.5L19 19l-.5 1.5-.5-1.5-1.5-.5 1.5-.5.5-1.5Z" /></>,
  stack: <><rect height="5" rx="1.5" width="15" x="4.5" y="4" /><rect height="5" rx="1.5" width="15" x="4.5" y="12.5" /><path d="M8 6.5h.01" /><path d="M8 15h.01" /></>,
  x: <><path d="m6.5 6.5 11 11" /><path d="m17.5 6.5-11 11" /></>,
}

interface IconProps {
  className?: string
  name: IconName
  /** 像素尺寸，默认 18。 */
  size?: number
}

/** 纯装饰图标：始终 aria-hidden，语义由外层按钮的 aria-label 承担。 */
export function Icon({ className, name, size = 18 }: IconProps): ReactElement {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      focusable="false"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="1.6"
      viewBox="0 0 24 24"
      width={size}
    >
      {PATHS[name]}
    </svg>
  )
}
