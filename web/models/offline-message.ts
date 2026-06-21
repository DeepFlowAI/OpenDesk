import type { AgentBrief, ChannelBrief, Conversation, GroupBrief, Message, VisitorBrief } from '@/models/conversation'

export type OfflineMessageStatus = 'pending' | 'converted'

export type OfflineMessageEntry = Omit<Message, 'conversation_id' | 'conversation_public_id'> & {
  offline_message_id: number
}

export type OfflineMessage = {
  id: number
  public_id: string
  tenant_id: number
  status: OfflineMessageStatus
  visitor: VisitorBrief | null
  channel: ChannelBrief | null
  target_group: GroupBrief | null
  conversation: Conversation | null
  visitor_external_id: string
  visitor_name: string | null
  handled_by_id: number | null
  handled_at: string | null
  last_message_at: string | null
  last_message_preview: string | null
  message_count: number
  metadata?: Record<string, unknown>
  created_at: string
  updated_at: string | null
}

export type OfflineMessageDetail = OfflineMessage & {
  messages: OfflineMessageEntry[]
  has_more_messages: boolean
  can_assign_self?: boolean
  can_assign_other?: boolean
}

export type OfflineMessageListResponse = {
  items: OfflineMessage[]
  has_more: boolean
  total?: number | null
}

export type OfflineMessageCountResponse = {
  total: number
}

export type OfflineMessageConvertResponse = {
  offline_message: OfflineMessage
  conversation: Conversation
  messages: Message[]
  assigned_to_current_user?: boolean
  assigned_agent?: AgentBrief | null
}
