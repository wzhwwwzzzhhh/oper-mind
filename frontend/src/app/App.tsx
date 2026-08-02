import type { ReactElement } from 'react'
import { useState } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'

import { ServiceCenterPage } from '../features/services/ServiceCenterPage'
import { Sidebar } from '../features/shell/Sidebar'
import { ThemeModal } from '../features/shell/ThemeModal'
import { TopBar } from '../features/shell/TopBar'
import { UtilityModal } from '../features/shell/UtilityModal'
import { UtilityRail, type UtilityKey } from '../features/shell/UtilityRail'
import { WorkbenchPage } from '../features/workbench/WorkbenchPage'
import { AppProviders } from './providers'

function ProductShell(): ReactElement {
  const [sidebar_collapsed, set_sidebar_collapsed] = useState(false)
  const [rail_collapsed, set_rail_collapsed] = useState(false)
  const [theme_modal_open, set_theme_modal_open] = useState(false)
  const [utility_open, set_utility_open] = useState(false)
  const [utility_key, set_utility_key] = useState<UtilityKey | null>(null)
  const [toast, set_toast] = useState<string | null>(null)

  const show_toast = (message: string): void => {
    set_toast(message)
    window.setTimeout(() => set_toast(null), 1800)
  }

  const shell_class = [
    'app-shell',
    sidebar_collapsed ? 'sidebar-collapsed' : '',
    rail_collapsed ? 'rail-collapsed' : '',
  ].join(' ')

  const open_utility = (key: UtilityKey): void => {
    set_utility_key(key)
    set_utility_open(true)
  }

  return (
    <div className={shell_class}>
      <Sidebar
        collapsed={sidebar_collapsed}
        on_collapse={() => set_sidebar_collapsed((value) => !value)}
      />
      <main className="workspace">
        <TopBar
          on_mobile_menu={() => set_sidebar_collapsed((value) => !value)}
          on_share={() => show_toast('分享链接功能将在接入会话 API 后启用')}
          on_theme={() => set_theme_modal_open(true)}
          on_utility={() => set_utility_open(true)}
        />
        <div className="chat-scroll">
          <div className="chat-inner">
            <Outlet />
          </div>
        </div>
      </main>
      <UtilityRail
        collapsed={rail_collapsed}
        on_collapse={() => set_rail_collapsed((value) => !value)}
        on_open_utility={open_utility}
      />
      <ThemeModal on_close={() => set_theme_modal_open(false)} open={theme_modal_open} />
      <UtilityModal
        on_close={() => set_utility_open(false)}
        open={utility_open}
        utility={utility_key}
      />
      {toast && <div className="toast show">{toast}</div>}
    </div>
  )
}

export function App(): ReactElement {
  return (
    <AppProviders>
      <BrowserRouter>
        <Routes>
          <Route element={<Navigate replace to="/workbench" />} path="/" />
          <Route element={<ProductShell />}>
            <Route path="/services">
              <Route element={<ServiceCenterPage />} index />
              <Route element={<ServiceCenterPage />} path=":service_id" />
            </Route>
            <Route path="/workbench">
              <Route element={<WorkbenchPage />} index />
              <Route element={<WorkbenchPage />} path="sessions/:session_id" />
              <Route element={<WorkbenchPage />} path="sessions/:session_id/runs/:run_id" />
            </Route>
          </Route>
          <Route element={<Navigate replace to="/workbench" />} path="*" />
        </Routes>
      </BrowserRouter>
    </AppProviders>
  )
}
