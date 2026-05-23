import type { ConditionItem } from '@/models/organization-view'
import type { CustomFieldValue } from '@/types/custom-field-value'

export type { CustomFieldValue } from '@/types/custom-field-value'

export type Organization = {
  id: number
  tenant_id: number
  public_id: string
  name: string
  description: string | null
  created_by: AuditActorRef | null
  updated_by: AuditActorRef | null
  custom_fields: Record<string, CustomFieldValue>
  user_count: number
  created_at: string
  updated_at: string
}

export type AuditActorRef = {
  actor_type: string | null
  actor_id: number | null
  actor_name: string | null
}

export type CreateOrganizationPayload = {
  name: string
  description?: string | null
  custom_fields?: Record<string, CustomFieldValue>
}

export type UpdateOrganizationPayload = {
  name?: string | null
  description?: string | null
  custom_fields?: Record<string, CustomFieldValue>
}

export type OrganizationQueryPayload = {
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

export type OrgViewCountItem = {
  view_id: number
  count: number
}

export type OrgViewCountsResponse = {
  total_count: number
  items: OrgViewCountItem[]
}
