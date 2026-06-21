export type EmojiItem = {
  emoji: string
  name: string
  name_en?: string | null
  alias?: string | null
  alias_en?: string | null
  keywords: string[]
}

export type EmojiTarget = 'user' | 'agent'

export type EmojiTargetPayload = {
  enabled: boolean
  emojis: EmojiItem[]
}

export type SaveEmojiSettingsPayload = {
  user: EmojiTargetPayload
  agent: EmojiTargetPayload
}

export type EmojiSettingConfig = SaveEmojiSettingsPayload & {
  id: number | null
  tenant_id: number | null
  configured: boolean
  updated_by_id: number | null
  updated_by_name: string | null
  updated_at: string | null
}

export type EmojiTargetConfig = {
  target: EmojiTarget
  configured: boolean
  enabled: boolean
  emojis: EmojiItem[]
  updated_at: string | null
}
