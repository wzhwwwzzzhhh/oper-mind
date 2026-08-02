import { create } from 'zustand'

/** 设计稿 5 主题，与 design-tokens.css 的 html[data-theme=...] 对应。 */
export const THEMES = [
  { key: 'steel', name: '钢蓝工作台', desc: '克制、清晰、偏企业级' },
  { key: 'indigo', name: '雾紫蓝', desc: '柔和、安静、偏编辑器' },
  { key: 'forest', name: '森林绿', desc: '稳定、自然、运维感更强' },
  { key: 'amber', name: '暖琥珀', desc: '温和、低刺激、暖白界面' },
  { key: 'night', name: '深夜模式', desc: '深色背景、适合夜间查看' },
] as const

export type ThemeKey = (typeof THEMES)[number]['key']

const STORAGE_KEY = 'opermind-theme'
const ALLOWED: ReadonlySet<string> = new Set(THEMES.map((theme) => theme.key))

function read_stored_theme(): ThemeKey {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (saved && ALLOWED.has(saved)) return saved as ThemeKey
  } catch {
    /* 无持久化时使用默认主题。 */
  }
  return 'steel'
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
