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
            <Typography.Text className="header-context">会话式多 Agent 运维诊断</Typography.Text>
          </div>
        </Header>
        <Content className="product-content">
          <div className="workspace-grid">
            <Outlet />
            <aside className="context-rail" aria-labelledby="context-title">
              <div className="rail-kicker">PRODUCT BOUNDARY</div>
              <Typography.Title id="context-title" level={4}>当前边界</Typography.Title>
              <Typography.Paragraph>
                在会话中提出运维问题，由多 Agent 协作调查并给出结论与安全 Trace；过程只展示安全摘要，不展示模型思维链。
              </Typography.Paragraph>
              <Typography.Paragraph type="secondary">
                受控工具、真实服务接入与监控仍在逐步接入；未接入的能力会如实标注。高风险动作必须经过提案、人工审批、白名单执行与验证。
              </Typography.Paragraph>
              <div className="honest-status" aria-label="能力状态">
                <span className="context-status">会话与多 Agent 内核：已接通</span>
                <span className="context-status">受控工具与真实证据：接入中</span>
                <span className="context-status">服务接入 / 监控 / 动作闭环：未启用</span>
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
