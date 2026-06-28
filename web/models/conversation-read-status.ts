export type ConversationReadStatusPayload = {
  agent_workspace_enabled: boolean
  web_sdk_enabled: boolean
}

export type ConversationReadStatusConfig = ConversationReadStatusPayload & {
  id: number | null
  tenant_id: number | null
  configured: boolean
  updated_by_id: number | null
  updated_by_name: string | null
  updated_at: string | null
}

export type ConversationReadStatusTargetConfig = {
  target: 'agent_workspace' | 'web_sdk'
  configured: boolean
  enabled: boolean
  updated_at: string | null
}

export type ConversationReadStatusPublicConfig = {
  web_sdk_enabled: boolean
}
