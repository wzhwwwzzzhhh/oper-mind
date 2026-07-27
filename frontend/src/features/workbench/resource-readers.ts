export function read_record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : undefined
}

export function read_string(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

export function read_boolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined
}

export function read_items(value: unknown): unknown[] {
  const record = read_record(value)
  return Array.isArray(record?.items) ? record.items : []
}

export function read_page(value: unknown): { has_more: boolean; next_cursor?: string } {
  const page = read_record(read_record(value)?.page)
  return {
    has_more: read_boolean(page?.has_more) ?? false,
    next_cursor: read_string(page?.next_cursor),
  }
}

export function resource_value(resource: unknown, key: string): unknown {
  return read_record(resource)?.[key]
}

export function resource_string(resource: unknown, key: string, fallback = '—'): string {
  return read_string(resource_value(resource, key)) ?? fallback
}

export function resource_optional_string(resource: unknown, key: string): string | undefined {
  return read_string(resource_value(resource, key))
}
