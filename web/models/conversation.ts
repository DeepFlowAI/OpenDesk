export type VisitorBrief = {
  id: number
  public_id: string
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
  public_id: string
  share_code: string
  tenant_id: number
  visitor: VisitorBrief | null
  agent: AgentBrief | null
  channel: ChannelBrief | null
  group: GroupBrief | null
  status: 'queued' | 'active' | 'bot' | 'handoff_pending' | 'closed'
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

export type VisitorWebStatus = 'online' | 'offline' | 'unknown'

export type VisitorWebStatusResponse = {
  conversation_id: number
  status: VisitorWebStatus
  can_display: boolean
  checked_at: string
}

export type MessageStatus = 'sending' | 'delivered' | 'read'

export type OpenAgentThinkingBlock = {
  id: string
  content: string
  llmStepId: number | null
  isStreaming: boolean
  timelineIndex: number
}

export type OpenAgentToolBlock = {
  id: string
  toolName: string
  brief: string
  toolCallId: string
  stepId: number | null
  isExecuting: boolean
  timelineIndex: number
  arguments?: unknown
  result?: unknown
  usedForHandoff?: boolean
}

export type OpenAgentTextBlock = {
  id: string
  content: string
  isStreaming: boolean
  timelineIndex: number
}

export type Message = {
  id: number
  conversation_id: number
  conversation_public_id?: string
  sender_type: 'visitor' | 'agent' | 'bot' | 'system'
  sender_id: number | null
  sender_name: string | null
  sender_avatar: string | null
  content_type: 'text' | 'image' | 'file' | 'system' | 'welcome' | 'satisfaction_event'
  content: string
  metadata?: Record<string, unknown>
  created_at: string
  status?: MessageStatus
  event_type?: 'invitation_sent' | 'feedback_submitted' | 'open_agent_handoff_event'
  satisfaction_record_id?: number
  config_version?: number
}

export type VisitorPublicMessage = Omit<Message, 'conversation_id'> & {
  conversation_id?: number
  conversation_public_id: string
}

export type MessageListResponse = {
  items: Message[]
  has_more: boolean
}

export type VisitorConversationHistoryItem = {
  conversation_public_id: string
  status: 'queued' | 'active' | 'bot' | 'handoff_pending' | 'closed'
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
  status: 'queued' | 'active' | 'bot' | 'handoff_pending' | 'closed'
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
