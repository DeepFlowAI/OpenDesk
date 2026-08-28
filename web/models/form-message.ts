import type { UnifiedField } from '@/models/field-definition'

export type PublicFormMessageField = {
  field_key: string | null
  field_id: number | null
  required: boolean
  definition: UnifiedField
}

export type PublicFormMessageConfig = {
  title: string
  description: string
  submit_label: string
  success_title: string
  success_description: string
  show_ticket_number: boolean
  fields: PublicFormMessageField[]
}

export type PublicFormMessageConfigResponse = {
  version: number
  config: PublicFormMessageConfig
}

export type FormMessageSource =
  | 'outside_service_hours'
  | 'queue_waiting'
  | 'queue_full'
  | 'bot_handoff'
  | 'bot_action'

export type PublicFormMessageSubmitPayload = {
  version: number
  idempotency_key: string
  values: Record<string, unknown>
  source: FormMessageSource
  conversation_public_id?: string | null
  queue_type?: 'employee_group' | null
  queue_id?: number | null
}

export type PublicFormMessageSubmitResponse = {
  ticket_id: number
  ticket_number: string | null
  success_title: string
  success_description: string
  show_ticket_number: boolean
  duplicated: boolean
}
