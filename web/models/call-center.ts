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
  /** True when Redis in-call legs still have an active consult after refresh. */
  consult_active?: boolean
  consult_target_employee_id?: number | null
  /** none | ringing | active — host consult lifecycle from server. */
  consult_state?: string | null
  /** When the agent entered in_call (Redis). Restores the timer without a CDR. */
  in_call_since?: string | null
  /** After-call work deadline (ISO). Drives the wrap-up countdown. */
  wrap_up_until?: string | null
  wrap_up_call_id?: string | null
  /** Server-owned business context restored after refresh/reconnect. */
  source?: string | null
  task_id?: number | null
  record_id?: number | null
}

export type AgentStatusUpdate = {
  status: AgentStatus
  reason?: string | null
}

export type ConsultableAgent = {
  employee_id: number
  name: string | null
  avatar: string | null
  status: AgentStatus
  /** Employee groups (queues) this agent belongs to; may be absent on old servers. */
  group_names?: string[]
}

/** Queue entry shown in the transfer target picker. */
export type TransferQueue = {
  queue_type: 'employee_group'
  queue_id: number
  name: string
  available_agent_count: number
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

export type CallRecordingItem = {
  recording_id: string
  call_leg_id: string | null
  phase: string | null
  status: 'recording' | 'completed' | 'partial' | 'failed' | string
  started_at: string | null
  ended_at: string | null
  duration_ms: number | null
  access_url: string | null
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
  public_id: string
  call_id: string
  direction: 'inbound' | 'outbound'
  call_source: 'inbound' | 'agent_dial' | 'manual_outbound_task' | 'auto_outbound' | string
  source?: string | null
  task_id?: number | null
  record_id?: number | null
  customer_number: string | null
  service_number: string | null
  lifecycle_status: 'active' | 'ended'
  finalization_status: 'pending' | 'completed' | 'incomplete' | 'failed' | null
  actual_reception_type: 'ivr' | 'bot' | 'agent' | 'bot_agent' | null
  call_result: string | null
  hangup_party: string | null
  hangup_reason_code: string | null
  initiator_agent_id: number | null
  initiator_agent_name: string | null
  last_serving_agent_id: number | null
  last_serving_agent_name: string | null
  user_id: number | null
  user_public_id: string | null
  user_name: string | null
  user_phone: string | null
  user_association_status: CallUserAssociationStatus
  started_at: string
  customer_connected_at: string | null
  first_agent_connected_at: string | null
  ended_at: string | null
  human_service_ended_at: string | null
  total_duration_ms: number | null
  customer_ring_duration_ms: number | null
  agent_wait_duration_ms: number | null
  customer_agent_talk_duration_ms: number | null
  satisfaction_result: 'not_surveyed' | 'completed' | 'partial' | 'unanswered' | 'failed' | null
  satisfaction_trigger_source: 'auto_transfer' | 'agent_invite' | null
  satisfaction_primary_option_id: string | null
  satisfaction_primary_option_label: string | null
  satisfaction_answer_count: number | null
  satisfaction_duration_ms: number | null
  recording_status: 'none' | 'recording' | 'completed' | 'partial' | 'failed'
  last_queue: QueueRecordBrief | null
}

export type CallRecordDetail = CallRecordListItem & {
  conversation_id: string | null
  root_call_id: string | null
  custom_business_info: string | null
  external_context: Record<string, unknown> | null
  voice_flow_id: number | null
  voice_flow_version_id: number | null
  result_rule_version: number | null
  finalized_at: string | null
  recordings: CallRecordingItem[]
  associated_user_candidates: CallRecordUserBrief[]
  related_tickets: RelatedTicket[]
  satisfaction: CallSatisfactionDetail | null
}

export type CallSatisfactionAnswerDetail = {
  question_node_id: string
  question_name: string
  option_id: string | null
  option_label: string | null
  answered_at: string | null
}

export type CallSatisfactionDetail = {
  status: 'preparing' | 'in_progress' | 'completed' | 'partial' | 'unanswered' | 'failed'
  trigger_source: 'auto_transfer' | 'agent_invite'
  flow_name: string
  flow_version_no: number
  started_at: string | null
  ended_at: string | null
  duration_ms: number | null
  agent_id: number | null
  agent_name: string | null
  queue_type: string | null
  queue_id: number | null
  queue_name: string | null
  termination_reason: string | null
  answers: CallSatisfactionAnswerDetail[]
}

export type CallRecordListResponse = PaginatedResponse<CallRecordListItem>

export type CallRecordAgentFilterOption = {
  id: number
  name: string
}

export type CallRecordQueueFilterOption = {
  queue_type: 'employee_group' | 'employee'
  queue_id: number
  name: string
}

export type CallRecordFilterOptionsResponse = {
  agents: CallRecordAgentFilterOption[]
  queues: CallRecordQueueFilterOption[]
}

export type CallTrajectoryEvent = {
  id: number
  event_id: string
  tenant_id: number
  call_record_id: number
  root_call_id: string
  event_type: string
  event_category: string
  schema_version: number
  occurred_at: string
  sequence_no: number
  operation_id: string | null
  call_leg_id: string | null
  parent_leg_id: string | null
  participant_role: string | null
  actor_type: string
  actor_id: string | null
  actor_name_snapshot: string | null
  target_type: string | null
  target_id: string | null
  target_name_snapshot: string | null
  queue_type: string | null
  queue_id: number | null
  queue_name_snapshot: string | null
  result: string | null
  reason_code: string | null
  reason_detail: string | null
  duration_ms: number | null
  source: string
  source_event_id: string | null
  trace_id: string | null
  is_synthetic: boolean
  details: Record<string, unknown>
  created_at: string
}

export type CallTrajectoryOperation = {
  operation_id: string
  event_ids: string[]
  started_at: string
  ended_at: string
  duration_ms: number
  result: string | null
}

export type CallTrajectoryResponse = {
  call_record_public_id: string
  call_id: string
  lifecycle_status: 'active' | 'ended'
  is_live: boolean
  is_complete: boolean
  last_updated_at: string | null
  total: number
  events: CallTrajectoryEvent[]
  operations: CallTrajectoryOperation[]
  settlement: CallTrajectoryEvent | null
  warnings: Array<{ code: string; message: string }>
}

export type CallTranscriptRole = 'user' | 'agent'

export type CallTranscriptSegment = {
  id: number
  role: CallTranscriptRole
  text: string
  seq: number | null
  created_at: string
}

export type CallTranscriptResponse = {
  call_id: string | null
  segments: CallTranscriptSegment[]
}

export type CallUserAssociationResponse = {
  record_public_id: string
  call_id: string
  identified_number: string | null
  normalized_number: string | null
  status: CallUserAssociationStatus
  user: CallRecordUserBrief | null
  candidates: CallRecordUserBrief[]
}
