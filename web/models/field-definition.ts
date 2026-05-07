import type { FieldDomain, FieldType, FieldSource, ApplicableModule } from '@/types/field-enums'

// ── Option ──

export type FdFieldOption = {
  id: number | null
  field_definition_id: number | null
  label: string
  value: string
  color: string | null
  sort_order: number
  is_active: boolean
  created_at: string | null
  updated_at: string | null
}

export type CreateFdFieldOptionPayload = {
  label: string
  value: string
  color?: string | null
  sort_order?: number
}

export type UpdateFdFieldOptionPayload = {
  label?: string
  value?: string
  color?: string | null
  sort_order?: number
  is_active?: boolean
}

// ── Tree Node ──

export type FdTreeNode = {
  id: number
  field_definition_id: number
  parent_id: number | null
  label: string
  value: string
  sort_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type CreateFdTreeNodePayload = {
  label: string
  value: string
  /** Batch create only: parent row index in this same array (0-based). */
  parent_index?: number
  parent_id?: number | null
  sort_order?: number
}

export type UpdateFdTreeNodePayload = {
  label?: string
  value?: string
  parent_id?: number | null
  sort_order?: number
  is_active?: boolean
}

// ── Field Definition (custom fields stored in DB) ──

export type FdFieldDefinition = {
  id: number
  tenant_id: number
  domain: FieldDomain
  source: FieldSource
  name: string
  description: string | null
  help_text: string | null
  field_type: FieldType
  type_config: Record<string, unknown>
  slot_column: string
  applicable_modules: ApplicableModule[] | null
  show_in_workspace: boolean | null
  status: string
  sort_order: number
  key: string | null
  options: FdFieldOption[]
  tree_nodes: FdTreeNode[]
  created_at: string
  updated_at: string
}

// ── Unified field (system + custom merged by backend) ──

export type UnifiedField = {
  key: string | null
  id: number | null
  domain: string
  source: 'system' | 'custom' | 'metadata'
  name: string
  description: string | null
  help_text: string | null
  field_type: FieldType
  type_config: Record<string, unknown>
  applicable_modules: ApplicableModule[] | null
  slot_column: string | null
  show_in_workspace: boolean | null
  sort_order: number
  status: string
  options: FdFieldOption[]
  tree_nodes: FdTreeNode[]
  created_at: string | null
  updated_at: string | null
}

export type CreateFdFieldDefinitionPayload = {
  domain: FieldDomain
  name: string
  description?: string | null
  help_text?: string | null
  field_type: FieldType
  type_config?: Record<string, unknown>
  source?: FieldSource
  applicable_modules?: ApplicableModule[] | null
  show_in_workspace?: boolean | null
  sort_order?: number
  options?: CreateFdFieldOptionPayload[] | null
  tree_nodes?: CreateFdTreeNodePayload[] | null
}

export type UpdateFdFieldDefinitionPayload = {
  name?: string
  description?: string | null
  help_text?: string | null
  type_config?: Record<string, unknown>
  applicable_modules?: ApplicableModule[] | null
  show_in_workspace?: boolean | null
  status?: string
  sort_order?: number
}

// ── System field override ──

export type SystemFieldOverridePayload = {
  show_in_workspace?: boolean
  sort_order?: number
  status?: string
}

// ── Sort ──

export type SortItem = {
  id?: number | null
  key?: string | null
  sort_order: number
}

export type SortPayload = {
  items: SortItem[]
}
