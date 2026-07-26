import { setupServer } from 'msw/node'

// P3.1 仅建立 MSW 测试基线；具体 v1 handler 留待 P3.2。
export const server = setupServer()