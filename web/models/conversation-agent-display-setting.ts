export type AgentDisplayMode = 'name' | 'nickname'

export type ConversationAgentDisplaySetting = {
  display_mode: AgentDisplayMode
  id: number | null
  tenant_id: number | null
  configured: boolean
  updated_by_id: number | null
  updated_by_name: string | null
  updated_at: string | null
}

export type ConversationAgentDisplaySettingPayload = {
  display_mode: AgentDisplayMode
}
