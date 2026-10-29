import type { UnifiedField } from '@/models/field-definition'
import type { TicketQueryPayload } from '@/models/ticket'

export type TicketExportConfig = {
  token: string
  prepared: {
    fields: UnifiedField[]
    summary: Record<string, string>
    query: Record<string, unknown>
    language: 'zh' | 'en'
  }
  signature: string
  count: number
}

export type TicketExportSource = {
  query: TicketQueryPayload
  columns: { field_id: number | null; field_key: string | null }[]
  language: 'zh' | 'en'
  timezone: string
}

export const exportFieldUid = (field: { id: number | null; key: string | null }) =>
  field.id != null ? `id:${field.id}` : `key:${field.key}`

export function exportColumnOrder(columns: TicketExportSource['columns'], fields: UnifiedField[]): string[] {
  const available = new Set(fields.map(exportFieldUid))
  const defaults = columns.map((column) => exportFieldUid({ id: column.field_id, key: column.field_key }))
  return [...new Set(['key:ticket_number', ...defaults.filter((uid) => available.has(uid))])]
}

export function orderedExportSelection(selected: string[], defaults: string[], fields: UnifiedField[]): string[] {
  const order = [...new Set(['key:ticket_number', ...defaults, ...fields.map(exportFieldUid)])]
  return order.filter((uid) => selected.includes(uid))
}
