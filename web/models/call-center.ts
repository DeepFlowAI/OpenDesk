import type { PaginatedResponse } from '@/models/common'
import type { RelatedTicket } from '@/models/ticket'

export type AgentStatus = 'ready' | 'busy' | 'break' | 'after_call_work' | 'offline'
export type AgentResourceState =
  | 'idle'
  | 'reserved'
  | 'ringing'
  | 'in_call'
  | 'after_call_work'
  | 'unavailable'

export type AgentStatusResponse = {
  employee_id: number
  status: AgentStatus
  reason: string | null
  status_changed_at: string | null
  updated_at: string | null
  resource_state?: AgentResourceState | null
  current_call_id?: string | null
  offer_id?: string | null
  queue_id?: number | null
  direction?: 'inbound' | 'outbound' | null
  reserved_until?: string | null
  resource_updated_at?: string | null
  last_release_reason?: string | null
}

export type AgentStatusUpdate = {
  status: AgentStatus
  reason?: string | null
}

export type CallUserAssociationStatus =
  | 'unknown'
  | 'unlinked'
  | 'linked'
  | 'created'
  | 'multiple'
  | 'failed'

export type CallRecordUserBrief = {
  id: number
  public_id: string
  name: string | null
  phone: string | null
  email: string | null
}

export type QueueRecordBrief = {
  queue_type: 'employee_group' | 'employee' | string
  queue_id: number
  name: string
}

export type WebRTCSession = {
  id: number
  employee_id: number
  webrtc_call_id: string
  state: 'online_idle' | 'busy' | 'disconnected'
  started_at: string
  ended_at: string | null
}

export type CallRecordListItem = {
  id: number
  call_id: string
  direction: 'inbound' | 'outbound'
  state: string
  from_number: string | null
  to_number: string | null
  employee_group_id: number | null
  agent_id: number | null
  agent_name: string | null
  user_id: number | null
  user_public_id: string | null
  user_name: string | null
  user_phone: string | null
  user_association_status: CallUserAssociationStatus
  started_at: string
  answered_at: string | null
  ended_at: string | null
  ring_duration_ms: number | null
  talk_duration_ms: number | null
  last_assigned_queue: QueueRecordBrief | null
  queue_duration_seconds: number | null
}

export type CallRecordDetail = CallRecordListItem & {
  conversation_id: string | null
  root_call_id: string | null
  voice_flow_id: number | null
  voice_flow_version_id: number | null
  hangup_reason: string | null
  recording_url: string | null
  recording_duration_ms: number | null
  metadata: Record<string, unknown>
  associated_user_candidates: CallRecordUserBrief[]
  related_tickets: RelatedTicket[]
}

export type CallRecordListResponse = PaginatedResponse<CallRecordListItem>

export type CallUserAssociationResponse = {
  record_id: number
  call_id: string
  identified_number: string | null
  normalized_number: string | null
  status: CallUserAssociationStatus
  user: CallRecordUserBrief | null
  candidates: CallRecordUserBrief[]
}
