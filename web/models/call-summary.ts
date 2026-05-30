import type { FdFieldDefinition } from '@/models/field-definition'

// ── Config ──

export type CallSummaryConfig = {
  id: number
  tenant_id: number
  status: string
  created_at: string
  updated_at: string
}

// ── Config Field ──

export type CallSummaryConfigField = {
  id: number
  config_id: number
  field_definition_id: number | null
  field_key: string | null
  sort_order: number
  is_active: boolean
  created_at: string
  updated_at: string
}

export type CallSummaryUsageField = CallSummaryConfigField & {
  field_definition: FdFieldDefinition | null
}

export type CreateCallSummaryConfigFieldPayload = {
  field_definition_id?: number | null
  field_key?: string | null
  is_active?: boolean
}

export type UpdateCallSummaryConfigFieldPayload = {
  is_active?: boolean
  sort_order?: number
}

export type CallSummaryConfigFieldListResponse = {
  items: CallSummaryConfigField[]
  total: number
}

export type CallSummaryUsageResponse = {
  call_record_id: number
  fields: CallSummaryUsageField[]
  rules: CallSummaryInteractionRule[]
  values: Record<string, unknown>
}

export type UpdateCallSummaryFieldValuePayload = {
  field_definition_id?: number | null
  field_key?: string | null
  value: unknown
}

export type CallSummaryFieldValue = {
  id: number | null
  tenant_id: number | null
  call_record_id: number
  field_definition_id: number | null
  field_key: string | null
  value: unknown
  created_at?: string | null
  updated_at?: string | null
}

// ── Interaction Rule ──

export type CallSummaryInteractionRule = {
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

export type CreateCallSummaryInteractionRulePayload = {
  name?: string | null
  condition_logic?: string
  conditions?: Record<string, unknown>[]
  actions?: Record<string, unknown>[]
  is_enabled?: boolean
  sort_order?: number
}

export type UpdateCallSummaryInteractionRulePayload = Partial<CreateCallSummaryInteractionRulePayload>

// ── Sort ──

export type SortItem = { id: number; sort_order: number }
