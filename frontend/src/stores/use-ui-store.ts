import { create } from 'zustand'

interface UiState {
  is_navigation_collapsed: boolean
  toggle_navigation: () => void
}

export const useUiStore = create<UiState>((set) => ({
  is_navigation_collapsed: false,
  toggle_navigation: () => {
    set((state) => ({ is_navigation_collapsed: !state.is_navigation_collapsed }))
  },
}))