import '@testing-library/jest-dom/vitest'
import { afterAll, afterEach, beforeAll } from 'vitest'

import { TestEventSource } from './event-source'
import { server } from './server'


class ResizeObserverMock {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  value: ResizeObserverMock,
})

Object.defineProperty(window, 'EventSource', {
  writable: true,
  value: TestEventSource,
})

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string): MediaQueryList => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  }),
})

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => {
  TestEventSource.reset()
  server.resetHandlers()
})
afterAll(() => server.close())