import type { FdFieldDefinition } from '@/models/field-definition'

// ── Config ──

export type CsSummaryConfig = {
  id: number
  tenant_id: number
  status: string
  created_at: string
  updated_at: string
}

// ── Config Field ──

export type CsSummaryConfigField = {
  id: number
  config_id: number
  field_definition_id: number | null
  field_key: string | null
  sort_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type CsSummaryUsageField = CsSummaryConfigField & {
  field_definition: FdFieldDefinition | null
}

export type CreateCsSummaryConfigFieldPayload = {
  field_definition_id?: number | null
  field_key?: string | null
  is_active?: boolean
}

export type UpdateCsSummaryConfigFieldPayload = {
  is_active?: boolean
  sort_order?: number
}

export type CsSummaryConfigFieldListResponse = {
  items: CsSummaryConfigField[]
  total: number
}

// ── Interaction Rule ──

export type CsSummaryInteractionRule = {
  id: number
  config_id: number
  name: string | null
  condition_logic: string
  conditions: Record<string, unknown>[]
  actions: Record<string, unknown>[]
  is_enabled: boolean
  sort_order: number
  created_at: string
  updated_at: string
}

export type CsSummaryUsageResponse = {
  conversation_id: number
  fields: CsSummaryUsageField[]
  rules: CsSummaryInteractionRule[]
  values: Record<string, unknown>
}

export type UpdateCsSummaryFieldValuePayload = {
  field_definition_id?: number | null
  field_key?: string | null
  value: unknown
}

export type CsSummaryFieldValue = {
  id: number | null
  tenant_id: number | null
  conversation_id: number
  field_definition_id: number | null
  field_key: string | null
  value: unknown
  created_at?: string | null
  updated_at?: string | null
}

export type CreateCsSummaryInteractionRulePayload = {
  name?: string | null
  condition_logic?: string
  conditions?: Record<string, unknown>[]
  actions?: Record<string, unknown>[]
  is_enabled?: boolean
  sort_order?: number
}

export type UpdateCsSummaryInteractionRulePayload = Partial<CreateCsSummaryInteractionRulePayload>

// ── Sort ──

export type SortItem = { id: number; sort_order: number }
