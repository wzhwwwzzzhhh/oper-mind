import { MenuFoldOutlined, MenuUnfoldOutlined, MonitorOutlined } from '@ant-design/icons'
import { Layout, Menu, Typography } from 'antd'
import type { ReactElement } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

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
          defaultSelectedKeys={['workbench']}
          items={[
            {
              key: 'workbench',
              icon: <MonitorOutlined />,
              label: '诊断工作台',
            },
          ]}
          mode="inline"
          theme="dark"
        />
        <div className="navigation-note">
          {!isNavigationCollapsed && 'V1 主产品 · 结果优先'}
        </div>
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
            <Typography.Text strong>主前端工作台</Typography.Text>
            <Typography.Text className="header-context">P3.1 产品外壳</Typography.Text>
          </div>
        </Header>
        <Content className="product-content">
          <div className="workspace-grid">
            <WorkbenchPage />
            <aside className="context-rail" aria-labelledby="context-title">
              <div className="rail-kicker">CURRENT CONTEXT</div>
              <Typography.Title id="context-title" level={4}>
                当前上下文
              </Typography.Title>
              <Typography.Paragraph>
                尚未选择诊断会话。P3.2 将从 <code>/api/v1/sessions</code> 恢复真实会话和 Run。
              </Typography.Paragraph>
              <Typography.Paragraph type="secondary">
                完整 Agent Trace 保持在研发界面 <code>report/</code>；当前产品外壳不会嵌入或模拟它。
              </Typography.Paragraph>
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
          <Route element={<ProductShell />} path="/workbench" />
          <Route element={<Navigate replace to="/workbench" />} path="*" />
        </Routes>
      </BrowserRouter>
    </AppProviders>
  )
}