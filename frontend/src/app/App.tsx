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
        <div className="navigation-note">{!isNavigationCollapsed && '个人 AI 运维助手 · 只读会话'}</div>
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
            <Typography.Text strong>个人会话</Typography.Text>
            <Typography.Text className="header-context">P3.6a · 只读 Turn 投影</Typography.Text>
          </div>
        </Header>
        <Content className="product-content">
          <div className="workspace-grid">
            <Outlet />
            <aside className="context-rail" aria-labelledby="context-title">
              <div className="rail-kicker">PRODUCT BOUNDARY</div>
              <Typography.Title id="context-title" level={4}>当前边界</Typography.Title>
              <Typography.Paragraph>
                页面以会话与消息为主线，按需展示已保存的调查摘要和结构化结论；不会把 Run、SSE 或 Trace 当作默认阅读对象。
              </Typography.Paragraph>
              <Typography.Paragraph type="secondary">
                当前仅恢复已有 v1 数据。发送、实时过程、监控、告警、审批和处理仍在后续切片，完整 Trace 继续仅面向研发界面。
              </Typography.Paragraph>
              <div className="honest-status" aria-label="阶段能力状态">
                <span className="context-status">发送与实时过程：后续 P3.6b</span>
                <span className="context-status">监控与数据源：待 P4</span>
                <span className="context-status">告警与受控处理：待 P5</span>
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
