import { setupServer } from 'msw/node'

import { api_v1_handlers } from './handlers'

export const server = setupServer(...api_v1_handlers)
