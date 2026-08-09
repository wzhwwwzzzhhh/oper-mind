import { create } from 'zustand'

/** 三套主题，与 design-tokens.css 的 :root / html[data-theme=...] 对应。
 *  差异是对比度策略而不是色相轮换：亮场值守、夜间值守、高对比。 */
export const THEMES = [
  { key: 'vellum', name: '蓝图亮色', desc: '冷调亮场，适合白天与共享屏幕' },
  { key: 'petrol', name: '深油青', desc: '低照度夜间值守，长时间盯屏更省眼' },
  { key: 'carbon', name: '高对比暗色', desc: '更强的文字与描边对比' },
] as const

export type ThemeKey = (typeof THEMES)[number]['key']

const STORAGE_KEY = 'opermind-theme'
const ALLOWED: ReadonlySet<string> = new Set(THEMES.map((theme) => theme.key))

/** 旧版 5 主题到新主题的迁移表，保住用户原本的明暗偏好。 */
const LEGACY_THEMES: Readonly<Record<string, ThemeKey>> = {
  amber: 'vellum',
  forest: 'vellum',
  indigo: 'vellum',
  night: 'petrol',
  steel: 'vellum',
}

function read_stored_theme(): ThemeKey {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (saved && ALLOWED.has(saved)) return saved as ThemeKey
    if (saved && saved in LEGACY_THEMES) return LEGACY_THEMES[saved] as ThemeKey
  } catch {
    /* 无持久化时使用默认主题。 */
  }
  return 'vellum'
}

function apply_theme(theme: ThemeKey): void {
  document.documentElement.dataset.theme = theme
}

interface ThemeState {
  theme: ThemeKey
  set_theme: (theme: ThemeKey) => void
}

export const useThemeStore = create<ThemeState>((set) => {
  const initial = read_stored_theme()
  apply_theme(initial)
  return {
    theme: initial,
    set_theme: (theme) => {
      if (!ALLOWED.has(theme)) return
      apply_theme(theme)
      try {
        window.localStorage.setItem(STORAGE_KEY, theme)
      } catch {
        /* 忽略持久化失败。 */
      }
      set({ theme })
    },
  }
})
