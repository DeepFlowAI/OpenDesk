export type UserStatFieldSettingsPayload = {
  show_session_count: boolean
  show_call_count: boolean
  show_unresolved_ticket_count: boolean
  show_total_ticket_count: boolean
}

export type UserStatFieldSettings = UserStatFieldSettingsPayload & {
  id: number | null
  tenant_id: number | null
  configured: boolean
  updated_by_id: number | null
  updated_by_name: string | null
  updated_at: string | null
}

export type ConversationUserStatisticItem = {
  key: 'calls' | 'sessions' | 'tickets'
  value: number | null
  unresolved_value: number | null
  total_value: number | null
}

export type ConversationUserStatistics = {
  conversation_id: number
  user_id: number | null
  items: ConversationUserStatisticItem[]
}
