import { CloudServerOutlined, MenuFoldOutlined, MenuUnfoldOutlined, MessageOutlined } from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import type { ReactElement } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom'

import { ServiceCenterPage } from '../features/services/ServiceCenterPage'
import { WorkbenchPage } from '../features/workbench/WorkbenchPage'
import { useUiStore } from '../stores/use-ui-store'
import { AppProviders } from './providers'

const { Header, Sider, Content } = Layout

function ProductShell(): ReactElement {
  const isNavigationCollapsed = useUiStore((state) => state.is_navigation_collapsed)
  const toggleNavigation = useUiStore((state) => state.toggle_navigation)
  const location = useLocation()
  const navigate = useNavigate()
  const selected_key = location.pathname.startsWith('/services') ? 'services' : 'conversations'

  return (
    <Layout className="product-shell">
      <Sider
        aria-label="主导航"
        breakpoint="lg"
        collapsed={isNavigationCollapsed}
        collapsedWidth={80}
        theme="dark"
        width={264}
      >
        <div className="brand" aria-label="OperMind">
          <span className="brand-mark">OM</span>
          {!isNavigationCollapsed && <span>OperMind</span>}
        </div>
        <Menu
          className="main-navigation"
          onClick={({ key }) => navigate(key === 'services' ? '/services' : '/workbench')}
          selectedKeys={[selected_key]}
          items={[
            { key: 'services', icon: <CloudServerOutlined />, label: '服务中心' },
            { key: 'conversations', icon: <MessageOutlined />, label: '我的会话' },
          ]}
          mode="inline"
          theme="dark"
        />
        <div className="navigation-note">{!isNavigationCollapsed && 'DevOps Copilot · 受控调查'}</div>
      </Sider>
      <Layout>
        <Header className="product-header">
          <button
            aria-label={isNavigationCollapsed ? '展开主导航' : '收起主导航'}
            className="navigation-trigger"
            onClick={toggleNavigation}
            type="button"
          >
            {isNavigationCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
          </button>
          <div>
            <Typography.Text strong>DevOps Copilot</Typography.Text>
            <Typography.Text className="header-context">P4.3 · 服务中心与受控调查入口</Typography.Text>
          </div>
        </Header>
        <Content className="product-content">
          <div className="workspace-grid">
            <Outlet />
            <aside className="context-rail" aria-labelledby="context-title">
              <div className="rail-kicker">PRODUCT BOUNDARY</div>
              <Typography.Title id="context-title" level={4}>当前边界</Typography.Title>
              <Typography.Paragraph>
                先在服务中心确认静态服务和当前有限快照，再进入会话完成证据化调查；过程只展示安全摘要。
              </Typography.Paragraph>
              <Typography.Paragraph type="secondary">
                当前只支持订单慢查询受控靶场。固定修复必须经过提案、人工审批、白名单执行与 Verify；不展示模型思维链。
              </Typography.Paragraph>
              <div className="honest-status" aria-label="阶段能力状态">
                <span className="context-status">服务中心与有限快照：P4.3</span>
                <span className="context-status">DB / 日志 / 服务证据：P4.1</span>
                <span className="context-status">审批、固定执行与验证：P4.2</span>
              </div>
            </aside>
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}

export function App(): ReactElement {
  return (
    <AppProviders>
      <BrowserRouter>
        <Routes>
          <Route element={<Navigate replace to="/services" />} path="/" />
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
          <Route element={<Navigate replace to="/services" />} path="*" />
        </Routes>
      </BrowserRouter>
    </AppProviders>
  )
}
