import { MenuFoldOutlined, MenuUnfoldOutlined, MonitorOutlined } from '@ant-design/icons'
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
        <div className="navigation-note">{!isNavigationCollapsed && 'V1 主产品 · 结果优先'}</div>
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
            <Typography.Text className="header-context">P3.2 只读恢复</Typography.Text>
          </div>
        </Header>
        <Content className="product-content">
          <div className="workspace-grid">
            <Outlet />
            <aside className="context-rail" aria-labelledby="context-title">
              <div className="rail-kicker">READ-ONLY BOUNDARY</div>
              <Typography.Title id="context-title" level={4}>
                当前边界
              </Typography.Title>
              <Typography.Paragraph>
                工作台只从 <code>/api/v1</code> 恢复 Session、Message 和 Run；刷新后的资源事实由服务端决定。
              </Typography.Paragraph>
              <Typography.Paragraph type="secondary">
                Run 受理与实时事件待 P3.3，结构化结果视觉待 P3.4；完整 Agent Trace 仍只在研发界面可用。
              </Typography.Paragraph>
              <div className="honest-status" aria-label="阶段能力状态">
                <span className="context-status">环境与数据源：待 P4</span>
                <span className="context-status">告警与审批：待 P5</span>
                <span className="context-status">报告与导出：待 P6</span>
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
