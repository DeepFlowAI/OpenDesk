import type { CustomFieldValue } from '@/types/custom-field-value'

export type EntityChangeValue =
  | CustomFieldValue
  | Record<string, unknown>
  | unknown[]

export type EntityChangeEntry = {
  field_key: string
  field_label: string
  old_value: EntityChangeValue
  new_value: EntityChangeValue
}

export type EntityChange = {
  id: number
  tenant_id: number
  entity_type: 'user' | 'organization' | string
  entity_id: number
  actor_type: string
  actor_id: number | null
  actor_name: string | null
  actor_avatar?: string | null
  field_key: string
  field_label: string
  field_source: string
  old_value: EntityChangeValue
  new_value: EntityChangeValue
  entries?: EntityChangeEntry[] | null
  created_at: string
  updated_at: string
}
