import type { ConditionItem } from '@/models/user-view'
import type { CustomFieldValue } from '@/types/custom-field-value'

export type { CustomFieldValue } from '@/types/custom-field-value'

export type User = {
  id: number
  tenant_id: number
  public_id: string
  external_id: string
  name: string
  email: string | null
  phone: string | null
  gender: string | null
  address: string | null
  remark: string | null
  web_id: string | null
  avatar_color: string | null
  channel_id: number | null
  organization_id: number | null
  created_by: AuditActorRef | null
  updated_by: AuditActorRef | null
  custom_fields: Record<string, CustomFieldValue>
  created_at: string
  updated_at: string
}

export type AuditActorRef = {
  actor_type: string | null
  actor_id: number | null
  actor_name: string | null
}

export type CreateUserPayload = {
  name: string
  email?: string | null
  phone?: string | null
  gender?: string | null
  address?: string | null
  remark?: string | null
  web_id?: string | null
  organization_id?: number | null
  custom_fields?: Record<string, CustomFieldValue>
}

export type UpdateUserPayload = {
  name?: string | null
  email?: string | null
  phone?: string | null
  gender?: string | null
  address?: string | null
  remark?: string | null
  web_id?: string | null
  organization_id?: number | null
  custom_fields?: Record<string, CustomFieldValue>
}

export type UserQueryPayload = {
  view_id?: number | null
  search?: string | null
  temp_conditions?: ConditionItem[]
  temp_condition_logic?: 'and' | 'or'
  group_value?: string | null
  sort_by?: string | null
  sort_order?: 'asc' | 'desc'
  page?: number
  per_page?: number
}

export type ViewCountItem = {
  view_id: number
  count: number
}

export type ViewCountsResponse = {
  total_count: number
  items: ViewCountItem[]
}
