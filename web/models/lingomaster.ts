export type LingoMasterSettings = {
  enabled: boolean
  visitor_prompt: string
  agent_prompt: string
  default_visitor_prompt: string
  default_agent_prompt: string
}

export type LingoMasterSettingsUpdate = Pick<
  LingoMasterSettings,
  'enabled' | 'visitor_prompt' | 'agent_prompt'
>

export type ConversationTranslationSettings = {
  global_enabled: boolean
  visitor_language: string | null
  visitor_language_source: 'browser' | 'detected' | 'manual' | null
  visitor_language_locked: boolean
  visitor_translation_enabled: boolean
  agent_translation_enabled: boolean
  visitor_translation_preference: boolean
  agent_translation_preference: boolean
  visitor_target_mode: 'agent' | 'fixed'
  visitor_target_language: string | null
  resolved_visitor_target_language: string | null
  agent_language: string
  updated_by: number | null
  updated_at: string | null
}

export type ConversationTranslationSettingsUpdate = {
  visitor_language_mode?: 'auto' | 'manual'
  visitor_language?: string
  visitor_translation_enabled?: boolean
  agent_translation_enabled?: boolean
  visitor_target_mode?: 'agent' | 'fixed'
  visitor_target_language?: string
}
