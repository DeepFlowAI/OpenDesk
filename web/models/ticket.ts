import type { ConditionItem } from '@/models/ticket-view'
import type { CustomFieldValue } from '@/types/custom-field-value'

export type { CustomFieldValue } from '@/types/custom-field-value'

export type Ticket = {
  id: number
  tenant_id: number
  ticket_number: string | null
  layout_id: number | null
  conversation_id: number | null
  conversation_public_id: string | null
  call_record_id: number | null
  call_record_call_id: string | null
  user_id: number | null
  agent_id: number | null
  assignee_group_id: number | null
  title: string
  description: string | null
  status: string
  priority: string | null
  created_by: AuditActorRef | null
  updated_by: AuditActorRef | null
  custom_fields: Record<string, CustomFieldValue>
  created_at: string
  updated_at: string
}

export type RelatedTicket = {
  id: number
  ticket_number: string | null
}

export type AuditActorRef = {
  actor_type: string | null
  actor_id: number | null
  actor_name: string | null
}

export type TicketChangeValue =
  | CustomFieldValue
  | Record<string, unknown>
  | unknown[]

export type TicketChangeEntry = {
  field_key: string
  field_label: string
  old_value: TicketChangeValue
  new_value: TicketChangeValue
}

export type TicketChange = {
  id: number
  tenant_id: number
  ticket_id: number
  actor_type: string
  actor_id: number | null
  actor_name: string | null
  /** Present when the actor is an employee with an uploaded profile photo. */
  actor_avatar?: string | null
  field_key: string
  field_label: string
  field_source: string
  old_value: TicketChangeValue
  new_value: TicketChangeValue
  /** Batched field updates from a single save (field_key = __batch__) */
  entries?: TicketChangeEntry[] | null
  created_at: string
  updated_at: string
}

export type CreateTicketPayload = {
  title: string
  description?: string | null
  status?: string
  priority?: string | null
  layout_id?: number | null
  conversation_id?: number | null
  call_record_id?: number | null
  user_id?: number | null
  agent_id?: number | null
  assignee_group_id?: number | null
  custom_fields?: Record<string, CustomFieldValue>
}

export type UpdateTicketPayload = {
  title?: string | null
  description?: string | null
  status?: string | null
  priority?: string | null
  conversation_id?: number | null
  call_record_id?: number | null
  user_id?: number | null
  agent_id?: number | null
  assignee_group_id?: number | null
  custom_fields?: Record<string, CustomFieldValue>
}

export type TicketQueryPayload = {
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

export type TicketViewCountItem = {
  view_id: number
  count: number
}

export type TicketViewCountsResponse = {
  total_count: number
  items: TicketViewCountItem[]
}
