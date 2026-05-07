export type VisitorBrief = {
  id: number
  external_id: string
  name: string
  avatar_color: string | null
}

export type AgentBrief = {
  id: number
  display_name: string | null
  name: string
  avatar: string | null
}

export type ChannelBrief = {
  id: number
  name: string
  channel_type: string
}

export type GroupBrief = {
  id: number
  name: string
}

export type Conversation = {
  id: number
  tenant_id: number
  visitor: VisitorBrief | null
  agent: AgentBrief | null
  channel: ChannelBrief | null
  group: GroupBrief | null
  status: 'queued' | 'active' | 'closed'
  started_at: string | null
  ended_at: string | null
  ended_by: string | null
  last_message_at: string | null
  last_message_preview: string | null
  unread_count: number
  has_history_conversations?: boolean
  created_at: string | null
}

export type ConversationListResponse = {
  items: Conversation[]
  total: number
}

export type MessageStatus = 'sending' | 'delivered' | 'read'

export type Message = {
  id: number
  conversation_id: number
  sender_type: 'visitor' | 'agent' | 'system'
  sender_id: number | null
  sender_name: string | null
  sender_avatar: string | null
  content_type: 'text' | 'image' | 'file' | 'system'
  content: string
  created_at: string
  status?: MessageStatus
}

export type MessageListResponse = {
  items: Message[]
  has_more: boolean
}

export type VisitorConversationHistoryItem = {
  id: number
  status: 'queued' | 'active' | 'closed'
  started_at: string | null
  ended_at: string | null
  last_message_at: string | null
  created_at: string | null
  agent_name: string | null
  agent_avatar: string | null
  messages: Message[]
  messages_truncated: boolean
}

export type VisitorConversationHistoryResponse = {
  items: VisitorConversationHistoryItem[]
  has_more: boolean
}

export type WorkspaceConversationHistoryItem = {
  id: number
  status: 'queued' | 'active' | 'closed'
  started_at: string | null
  ended_at: string | null
  last_message_at: string | null
  created_at: string | null
  channel: ChannelBrief | null
  agent: AgentBrief | null
  messages: Message[]
  messages_truncated: boolean
}

export type WorkspaceConversationHistoryResponse = {
  items: WorkspaceConversationHistoryItem[]
  has_more: boolean
}

export type AgentStatus = {
  user_id: number
  status: 'online' | 'busy' | 'offline'
  current_count: number
  max_concurrent: number
}

export type AgentStats = {
  current_count: number
  max_concurrent: number
}
