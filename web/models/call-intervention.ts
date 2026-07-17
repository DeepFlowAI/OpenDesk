import type { EmployeeBrief } from '@/models/session-report'

export type CallPhase = 'single' | 'customer_hold' | 'consulting' | 'three_way' | 'transferring'

export type InterventionMode = 'listen' | 'whisper' | 'barge' | 'takeover' | 'force_hangup'

export type CallDirection = 'inbound' | 'outbound'

export type SupervisorBrief = {
  employee_id: number
  name: string
  mode: InterventionMode
}

export type LiveCallRow = {
  call_id: string
  conversation_id: string | null
  agent: EmployeeBrief
  masked_customer_number: string
  direction: CallDirection
  queue_name: string | null
  phase: CallPhase
  answered_at: string | null
  talk_duration_seconds: number
  current_supervisor: SupervisorBrief | null
}

export type LiveCallsResponse = {
  items: LiveCallRow[]
  as_of: string
}

export type InterventionReasonPayload = {
  reason: string
  note?: string
}

export type InterventionResult = {
  ok: boolean
  call_id: string
  mode: InterventionMode
  supervisor_id: number
}
