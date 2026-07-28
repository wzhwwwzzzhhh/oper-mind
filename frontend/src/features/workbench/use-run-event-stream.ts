import type { Dispatch, SetStateAction } from 'react'
import { useEffect, useRef, useState } from 'react'

import { is_terminal_run_event, read_sse_run_event, type PersistedRunEvent } from './run-events'

export type EventStreamState = 'connected' | 'connecting' | 'idle' | 'recovering'

interface UseRunEventStreamOptions {
  enabled: boolean
  on_event: Dispatch<SetStateAction<PersistedRunEvent[]>>
  on_recover: () => Promise<void>
  on_terminal: () => Promise<void>
  run_id: string
}

export function use_run_event_stream({
  enabled,
  on_event,
  on_recover,
  on_terminal,
  run_id,
}: UseRunEventStreamOptions): EventStreamState {
  const [state, set_state] = useState<EventStreamState>('idle')
  const recovering = useRef(false)

  useEffect(() => {
    if (!enabled || !run_id) {
      set_state('idle')
      return undefined
    }

    recovering.current = false
    set_state('connecting')
    const source = new window.EventSource(`/api/v1/runs/${encodeURIComponent(run_id)}/stream`)
    const recover = async (): Promise<void> => {
      if (recovering.current) return
      recovering.current = true
      set_state('recovering')
      try {
        await on_recover()
      } finally {
        recovering.current = false
      }
    }
    const on_open = (): void => set_state('connected')
    const on_message = (message: MessageEvent<string>): void => {
      const event = read_sse_run_event(message.data, run_id)
      if (!event) return

      on_event((current_events) => {
        if (current_events.some((current_event) => current_event.sequence === event.sequence)) {
          return current_events
        }
        return [...current_events, event].sort((left, right) => left.sequence - right.sequence)
      })
      if (is_terminal_run_event(event)) {
        source.close()
        set_state('idle')
        void on_terminal()
      }
    }
    const on_error = (): void => {
      void recover()
    }

    source.addEventListener('open', on_open)
    source.addEventListener('run_event', on_message as EventListener)
    source.addEventListener('error', on_error)
    return () => {
      source.removeEventListener('open', on_open)
      source.removeEventListener('run_event', on_message as EventListener)
      source.removeEventListener('error', on_error)
      source.close()
    }
  }, [enabled, on_event, on_recover, on_terminal, run_id])

  return state
}
