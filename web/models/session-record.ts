import type { SatisfactionSummary } from './satisfaction-survey'
import type { RelatedTicket } from './ticket'

export type SessionRecordVisitor = {
  id: number
  public_id: string
  external_id: string
  name: string
  avatar_color: string | null
}

export type SessionRecordAgent = {
  id: number
  name: string
  display_name: string | null
  avatar: string | null
}

export type SessionRecordChannel = {
  id: number
  name: string
  channel_type: string
}

export type QueueRecordBrief = {
  queue_type: 'employee_group' | 'employee' | string
  queue_id: number
  name: string
}

export type SessionRecordType = 'human' | 'bot' | 'bot_human'

export type BotHandoffStatus =
  | 'not_triggered'
  | 'waiting_confirmation'
  | 'handoff_in_progress'
  | 'in_queue'
  | 'succeeded'
  | 'failed'
  | 'dismissed'

export type QueueResult =
  | 'assigned'
  | 'canceled'
  | 'timeout'
  | 'waiting'
  | 'failed'

export type ReceptionParticipant = {
  agent_id: number
  name: string | null
}

export type ReceptionGenerationStatus = 'generated' | 'failed' | null

export type ReceptionSegment = {
  seq_no: number
  agent_id: number | null
  agent_name: string | null
  group_id: number | null
  group_name: string | null
  started_at: string
  ended_at: string | null
  duration_seconds: number | null
  entry_reason: string
  end_reason: string | null
  from_agent_id: number | null
  to_agent_id: number | null
  visitor_message_count: number
  agent_message_count: number
  first_response_seconds: number | null
  avg_response_seconds: number | null
}

export type ReceptionTrajectory = {
  conversation_id: number
  conversation_status: SessionRecord['status']
  generation_status: ReceptionGenerationStatus
  segments: ReceptionSegment[]
}

export type SessionRecord = {
  id: number
  public_id: string
  share_code: string
  session_type: SessionRecordType | null
  bot_handoff_status: BotHandoffStatus | null
  visitor: SessionRecordVisitor | null
  agent: SessionRecordAgent | null
  channel: SessionRecordChannel | null
  status: 'queued' | 'active' | 'bot' | 'handoff_pending' | 'closed'
  started_at: string | null
  ended_at: string | null
  ended_by: string | null
  duration_seconds: number | null
  visitor_system: string | null
  visitor_browser: string | null
  visitor_ip: string | null
  created_at: string | null
  message_count: number
  visitor_message_count: number
  agent_message_count: number
  bot_phase_message_count: number
  human_phase_message_count: number
  human_phase_visitor_message_count: number
  human_phase_agent_message_count: number
  satisfaction: SatisfactionSummary | null
  last_assigned_queue: QueueRecordBrief | null
  queue_duration_seconds: number | null
  first_human_response_seconds: number | null
  agent_response_count: number | null
  agent_avg_response_seconds: number | null
  has_queue: boolean
  queue_entered_at: string | null
  queue_assigned_at: string | null
  queue_result: QueueResult | null
  reception_segment_count: number
  reception_transfer_count: number
  reception_final_agent_id: number | null
  reception_participants: ReceptionParticipant[]
  reception_generation_status: ReceptionGenerationStatus
}

export type SessionRecordListResponse = {
  items: SessionRecord[]
  total: number
  page: number
  per_page: number
  pages: number
}

export type SessionRecordDetail = SessionRecord & {
  last_message_preview: string | null
  related_tickets: RelatedTicket[]
}

export type SessionRecordMessage = {
  id: number
  conversation_id: number
  sender_type: 'visitor' | 'agent' | 'bot' | 'system'
  sender_id: number | null
  sender_name: string | null
  sender_avatar: string | null
  content_type: 'text' | 'rich_text' | 'image' | 'file' | 'system' | 'welcome' | 'bot_welcome' | 'satisfaction_event' | 'internal_note'
  content: string
  metadata?: Record<string, unknown>
  created_at: string
  event_type?: string
  satisfaction_record_id?: number
  config_version?: number
}

export type SessionRecordMessageListResponse = {
  items: SessionRecordMessage[]
  has_more: boolean
}

export type SessionRecordFilters = {
  page: number
  per_page: number
  start_date?: string
  end_date?: string
  agent_id?: number
  visitor_id?: number
  session_type?: SessionRecordType
  has_queue?: boolean
  keyword?: string
  satisfaction_status?: string
  satisfaction_resolved?: string
  satisfaction_service_option?: string
  satisfaction_service_label?: string
  satisfaction_product_option?: string
  satisfaction_product_label?: string
}
