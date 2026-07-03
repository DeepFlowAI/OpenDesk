export type KnowledgeInputSuggestionSetting = {
  enabled: boolean
  trigger_length: number
  id: number | null
  tenant_id: number | null
  configured: boolean
  updated_by_id: number | null
  updated_by_name: string | null
  updated_at: string | null
}

export type KnowledgeInputSuggestionSettingPayload = {
  enabled: boolean
  trigger_length: number
}
