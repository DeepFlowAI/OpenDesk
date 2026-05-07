export type SessionRecordVisitor = {
  id: number
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

export type SessionRecord = {
  id: number
  visitor: SessionRecordVisitor | null
  agent: SessionRecordAgent | null
  channel: SessionRecordChannel | null
  status: 'queued' | 'active' | 'closed'
  started_at: string | null
  ended_at: string | null
  ended_by: string | null
  created_at: string | null
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
}

export type SessionRecordMessage = {
  id: number
  conversation_id: number
  sender_type: 'visitor' | 'agent' | 'system'
  sender_id: number | null
  sender_name: string | null
  sender_avatar: string | null
  content_type: 'text' | 'image' | 'file' | 'system'
  content: string
  created_at: string
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
}
