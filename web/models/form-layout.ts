import type { FieldDefaultState } from '@/types/field-enums'

// ── Field placement (leaf) ──

export type FieldSource = 'ticket' | 'ticket_metadata' | 'user' | 'organization'

export type FdFormLayoutField = {
  id: number
  section_id: number
  field_definition_id: number | null
  field_key: string | null
  field_source: FieldSource
  default_state: FieldDefaultState
  column_span: number
  sort_order: number
  created_at: string
  updated_at: string
}

export type CreateFdFormLayoutFieldPayload = {
  field_definition_id?: number | null
  field_key?: string | null
  field_source?: FieldSource
  default_state?: FieldDefaultState
  column_span?: number
  sort_order?: number
}

// ── Section (inside a tab) ──

export type FdFormLayoutSection = {
  id: number
  tab_id: number
  name: string
  sort_order: number
  is_collapsed: boolean
  fields: FdFormLayoutField[]
  created_at: string
  updated_at: string
}

export type CreateFdFormLayoutSectionPayload = {
  name: string
  sort_order?: number
  is_collapsed?: boolean
  fields?: CreateFdFormLayoutFieldPayload[]
}

// ── Tab (outermost container) ──

export type FdFormLayoutTab = {
  id: number
  layout_id: number
  name: string
  sort_order: number
  sections: FdFormLayoutSection[]
  created_at: string
  updated_at: string
}

export type CreateFdFormLayoutTabPayload = {
  name: string
  sort_order?: number
  sections?: CreateFdFormLayoutSectionPayload[]
}

// ── Layout ──

export type FdFormLayout = {
  id: number
  tenant_id: number
  name: string
  scene: string
  columns_per_row: number
  label_position: string
  status: string
  tabs: FdFormLayoutTab[]
  created_at: string
  updated_at: string
}

export type FdFormLayoutSummary = {
  id: number
  tenant_id: number
  name: string
  scene: string
  columns_per_row: number
  label_position: string
  status: string
  created_at: string
  updated_at: string
}

export type CreateFdFormLayoutPayload = {
  name: string
  scene: string
  columns_per_row?: number
  label_position?: string
  tabs?: CreateFdFormLayoutTabPayload[]
}

export type UpdateFdFormLayoutPayload = {
  name?: string
  columns_per_row?: number
  label_position?: string
  status?: string
  tabs?: CreateFdFormLayoutTabPayload[]
}
