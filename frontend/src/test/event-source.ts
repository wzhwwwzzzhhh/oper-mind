export class TestEventSource extends EventTarget {
  static instances: TestEventSource[] = []

  readonly url: string
  closed = false

  constructor(url: string) {
    super()
    this.url = url
    TestEventSource.instances.push(this)
  }

  close(): void {
    this.closed = true
  }

  emit_open(): void {
    this.dispatchEvent(new Event('open'))
  }

  emit_error(): void {
    this.dispatchEvent(new Event('error'))
  }

  emit_run_event(payload: unknown): void {
    this.dispatchEvent(new MessageEvent('run_event', { data: JSON.stringify(payload) }))
  }

  static reset(): void {
    TestEventSource.instances = []
  }
}
