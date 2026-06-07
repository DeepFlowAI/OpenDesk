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

export type SessionRecord = {
  id: number
  public_id: string
  share_code: string
  visitor: SessionRecordVisitor | null
  agent: SessionRecordAgent | null
  channel: SessionRecordChannel | null
  status: 'queued' | 'active' | 'bot' | 'handoff_pending' | 'closed'
  started_at: string | null
  ended_at: string | null
  ended_by: string | null
  created_at: string | null
  satisfaction: SatisfactionSummary | null
  last_assigned_queue: QueueRecordBrief | null
  queue_duration_seconds: number | null
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
  content_type: 'text' | 'image' | 'file' | 'system' | 'welcome' | 'satisfaction_event'
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
  keyword?: string
  satisfaction_status?: string
  satisfaction_resolved?: string
  satisfaction_service_option?: string
  satisfaction_service_label?: string
  satisfaction_product_option?: string
  satisfaction_product_label?: string
}
