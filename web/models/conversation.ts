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
  visitor_system: string | null
  visitor_browser: string | null
  visitor_ip: string | null
  unread_count: number
  is_pinned?: boolean
  pinned_at?: string | null
  is_timeout_locked?: boolean
  timeout_locked_at?: string | null
  timeout_locked_by_id?: number | null
  has_history_conversations?: boolean
  viewer_relation?: 'own' | 'peer' | 'collaborator' | null
  collaborated_by_current_user?: boolean
  collaborators?: AgentBrief[]
  created_at: string | null
}

export type ConversationListResponse = {
  items: Conversation[]
  total: number
}

export type ConversationHistoryListResponse = {
  items: Conversation[]
  total: number
  has_more: boolean
}

export type StartConversationFromHistoryResponse = {
  conversation: Conversation
  is_new: boolean
  already_active: boolean
}

export type VisitorWebStatus = 'online' | 'offline' | 'unknown'

export type VisitorWebStatusResponse = {
  conversation_id: number
  status: VisitorWebStatus
  can_display: boolean
  checked_at: string
}

export type MessageStatus = 'sending' | 'delivered' | 'unread' | 'read'

export type MessageQuote = {
  schema_version: 1
  message_id: number
  sender_type: Message['sender_type']
  sender_id: number | null
  sender_name: string | null
  content_type: Message['content_type']
  summary?: string
  file_name?: string
  is_recalled?: boolean
}

export type MessageMetadata = Record<string, unknown> & {
  quote?: MessageQuote
}

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
  content_type: 'text' | 'rich_text' | 'image' | 'file' | 'system' | 'welcome' | 'bot_welcome' | 'satisfaction_event' | 'internal_note'
  content: string
  is_recalled?: boolean
  recalled_at?: string | null
  recalled_by_type?: 'visitor' | 'agent' | 'bot' | 'system' | string | null
  recalled_by_id?: number | null
  recalled_by_name?: string | null
  metadata?: MessageMetadata
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

export type VisitorUnreadOfflineReplyItem = VisitorConversationHistoryItem & {
  offline_message_public_id: string
  customer_unread_at: string
  customer_unread_message_id: number | null
  offline_reply_unread: boolean
}

export type VisitorUnreadOfflineReplyResponse = {
  items: VisitorUnreadOfflineReplyItem[]
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

export type WorkspaceMessageSearchConversation = {
  id: number
  share_code: string
  status: 'queued' | 'active' | 'bot' | 'handoff_pending' | 'closed'
  started_at: string | null
  channel: ChannelBrief | null
}

export type WorkspaceMessageSearchResult = {
  id: number
  conversation_id: number
  sender_type: Message['sender_type']
  sender_id: number | null
  sender_name: string | null
  sender_avatar: string | null
  content_type: Message['content_type']
  content: string
  is_recalled?: boolean
  recalled_at?: string | null
  recalled_by_type?: string | null
  recalled_by_id?: number | null
  recalled_by_name?: string | null
  created_at: string
  conversation: WorkspaceMessageSearchConversation
}

export type WorkspaceMessageSearchResponse = {
  items: WorkspaceMessageSearchResult[]
  total: number
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
