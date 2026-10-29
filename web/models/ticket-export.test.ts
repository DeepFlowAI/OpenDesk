import { expect, it } from 'vitest'
import { exportColumnOrder, exportFieldUid, orderedExportSelection } from '@/models/ticket-export'
import type { UnifiedField } from '@/models/field-definition'

const fields = [
  { id: null, key: 'ticket_number', name: 'Number' },
  { id: null, key: 'title', name: 'Same' },
  { id: 7, key: 'custom_key', name: 'Same' },
  { id: null, key: 'updated_at', name: 'Updated' },
] as UnifiedField[]
it('uses custom IDs even when a custom field also has a key', () => {
  expect(exportFieldUid(fields[2])).toBe('id:7')
})
it('pins number and preserves actual list order without adding missing columns', () => {
  const columns = [{ field_id: 7, field_key: 'custom_key' }, { field_id: null, field_key: 'title' }, { field_id: null, field_key: 'missing' }]
  expect(exportColumnOrder(columns, fields)).toEqual(['key:ticket_number', 'id:7', 'key:title'])
  expect(columns).toHaveLength(3)
})
it('additional selections follow catalog order, independently of click order', () => {
  expect(orderedExportSelection(['id:7', 'key:updated_at', 'key:ticket_number', 'key:title'], ['key:ticket_number', 'key:title'], fields))
    .toEqual(['key:ticket_number', 'key:title', 'id:7', 'key:updated_at'])
})
