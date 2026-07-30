import { MenuFoldOutlined, MenuUnfoldOutlined, MessageOutlined } from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import type { ReactElement } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'

import { WorkbenchPage } from '../features/workbench/WorkbenchPage'
import { useUiStore } from '../stores/use-ui-store'
import { AppProviders } from './providers'

const { Header, Sider, Content } = Layout

function ProductShell(): ReactElement {
  const isNavigationCollapsed = useUiStore((state) => state.is_navigation_collapsed)
  const toggleNavigation = useUiStore((state) => state.toggle_navigation)

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
          defaultSelectedKeys={['conversations']}
          items={[{ key: 'conversations', icon: <MessageOutlined />, label: '我的会话' }]}
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
            <Typography.Text className="header-context">P4.1 · 订单慢查询只读调查</Typography.Text>
          </div>
        </Header>
        <Content className="product-content">
          <div className="workspace-grid">
            <Outlet />
            <aside className="context-rail" aria-labelledby="context-title">
              <div className="rail-kicker">PRODUCT BOUNDARY</div>
              <Typography.Title id="context-title" level={4}>当前边界</Typography.Title>
              <Typography.Paragraph>
                页面以会话与消息为主线；调查过程只展示角色、状态、耗时和安全摘要，证据与结论按需展开。
              </Typography.Paragraph>
              <Typography.Paragraph type="secondary">
                当前只支持订单慢查询的只读调查；不执行修复、不展示模型思维链，也不把 Trace 当作产品主界面。
              </Typography.Paragraph>
              <div className="honest-status" aria-label="阶段能力状态">
                <span className="context-status">会话与只读调查：P4.1</span>
                <span className="context-status">DB / 日志 / 服务证据：P4.1</span>
                <span className="context-status">审批、修复与验证：待 P4.2</span>
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
          <Route element={<ProductShell />} path="/workbench">
            <Route element={<WorkbenchPage />} index />
            <Route element={<WorkbenchPage />} path="sessions/:session_id" />
            <Route element={<WorkbenchPage />} path="sessions/:session_id/runs/:run_id" />
          </Route>
          <Route element={<Navigate replace to="/workbench" />} path="*" />
        </Routes>
      </BrowserRouter>
    </AppProviders>
  )
}
