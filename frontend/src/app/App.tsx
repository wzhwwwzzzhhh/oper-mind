import type { ReactElement } from 'react'
import { useState } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'

import { ServiceCenterPage } from '../features/services/ServiceCenterPage'
import { ServiceDetailPage } from '../features/services/ServiceDetailPage'
import { MonitoringOverviewPage } from '../features/monitor/MonitoringOverviewPage'
import { KnowledgePage } from '../features/knowledge/KnowledgePage'
import { ModelSettingsPage } from '../features/models/ModelSettingsPage'
import { ApprovalDetailPage, ApprovalsPage } from '../features/approvals/ApprovalsPage'
import { GlobalNav } from '../features/shell/GlobalNav'
import { ServiceContextNav } from '../features/shell/ServiceContextNav'
import { Sidebar } from '../features/shell/Sidebar'
import { ThemeModal } from '../features/shell/ThemeModal'
import { TopBar } from '../features/shell/TopBar'
import { WorkbenchPage } from '../features/workbench/WorkbenchPage'
import { AppProviders } from './providers'

function ProductShell(): ReactElement {
  const [sidebar_collapsed, set_sidebar_collapsed] = useState(false)
  const [theme_modal_open, set_theme_modal_open] = useState(false)
  const [toast, set_toast] = useState<string | null>(null)
  const location = useLocation()
  const is_services = location.pathname.startsWith('/services')
  const is_models = location.pathname.startsWith('/models')
  const is_monitor = location.pathname.startsWith('/monitor')
  const is_knowledge = location.pathname.startsWith('/knowledge')
  const is_operations = is_services || is_models || is_monitor || is_knowledge

  const show_toast = (message: string): void => {
    set_toast(message)
    window.setTimeout(() => set_toast(null), 1800)
  }

  return (
    <div className={`app-shell${is_operations ? ' mode-service' : ' mode-chat'}`}>
      <GlobalNav />
      {/* 第二栏：随模式切换（会话侧栏 / 服务中心上下文） */}
      {is_operations ? <ServiceContextNav /> : <Sidebar collapsed={sidebar_collapsed} on_collapse={() => set_sidebar_collapsed((value) => !value)} />}
      <main className="workspace">
        <TopBar
          on_theme={() => set_theme_modal_open(true)}
          on_share={() => show_toast('分享链接功能将在接入权限系统后启用')}
        />
        <div className="main-scroll">
          <Outlet />
        </div>
      </main>
      <ThemeModal on_close={() => set_theme_modal_open(false)} open={theme_modal_open} />
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
              <Route element={<ServiceDetailPage />} path=":service_id" />
            </Route>
            <Route element={<MonitoringOverviewPage />} path="/monitor" />
            <Route element={<ModelSettingsPage />} path="/models" />
            <Route element={<KnowledgePage />} path="/knowledge" />
            <Route path="/workbench">
              <Route element={<WorkbenchPage />} index />
              <Route element={<WorkbenchPage />} path="sessions/:session_id" />
              <Route element={<WorkbenchPage />} path="sessions/:session_id/runs/:run_id" />
              <Route element={<ApprovalsPage />} path="approvals" />
              <Route element={<ApprovalDetailPage />} path="approvals/:proposal_id" />
            </Route>
          </Route>
          <Route element={<Navigate replace to="/workbench" />} path="*" />
        </Routes>
      </BrowserRouter>
    </AppProviders>
  )
}
