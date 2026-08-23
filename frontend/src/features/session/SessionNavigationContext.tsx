import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { Dispatch, PropsWithChildren, ReactElement, SetStateAction } from 'react'

export type SessionListView = 'active' | 'archived'

interface SessionNavigationValue {
  lifecycle_notice: string | null
  search_query: string
  search_value: string
  set_lifecycle_notice: (notice: string | null) => void
  set_search_query: Dispatch<SetStateAction<string>>
  set_search_value: Dispatch<SetStateAction<string>>
  set_view: Dispatch<SetStateAction<SessionListView>>
  view: SessionListView
}

const SessionNavigationContext = createContext<SessionNavigationValue | null>(null)

/** 在会话侧栏与详情之间共享纯导航状态；服务器会话事实仍只来自 API。 */
export function SessionNavigationProvider({ children }: PropsWithChildren): ReactElement {
  const [view, set_view] = useState<SessionListView>('active')
  const [search_value, set_search_value] = useState('')
  const [search_query, set_search_query] = useState('')
  const [lifecycle_notice, set_lifecycle_notice] = useState<string | null>(null)
  const [notice_revision, set_notice_revision] = useState(0)
  const publish_lifecycle_notice = useCallback((notice: string | null): void => {
    set_lifecycle_notice(notice)
    set_notice_revision((current) => current + 1)
  }, [])
  useEffect(() => {
    if (lifecycle_notice === null) return undefined
    const timeout = window.setTimeout(() => set_lifecycle_notice(null), 5000)
    return () => window.clearTimeout(timeout)
  }, [lifecycle_notice, notice_revision])
  const value = useMemo(
    () => ({
      lifecycle_notice,
      search_query,
      search_value,
      set_lifecycle_notice: publish_lifecycle_notice,
      set_search_query,
      set_search_value,
      set_view,
      view,
    }),
    [lifecycle_notice, publish_lifecycle_notice, search_query, search_value, view],
  )

  return <SessionNavigationContext.Provider value={value}>{children}</SessionNavigationContext.Provider>
}

export function use_session_navigation(): SessionNavigationValue {
  const value = useContext(SessionNavigationContext)
  if (value === null) throw new Error('SessionNavigationProvider 未装配。')
  return value
}
