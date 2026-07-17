export type CallPromptScene = 'hold' | 'consult' | 'three_party' | 'transfer'
export type CallPromptType = 'tts' | 'audio'
export type CallPromptPlayMode = 'loop_15s' | 'once'

export type CallPromptTone = {
  scene: CallPromptScene
  enabled: boolean
  prompt_type: CallPromptType
  tts_text: string | null
  audio_asset_id: number | null
  play_mode: CallPromptPlayMode
}

export type CallPromptToneSettings = {
  scenes: CallPromptTone[]
}

export type CallPromptToneItemPayload = {
  scene: CallPromptScene
  enabled: boolean
  prompt_type: CallPromptType
  tts_text: string | null
  audio_asset_id: number | null
}

export type UpdateCallPromptTonesPayload = {
  scenes: CallPromptToneItemPayload[]
}

export const CALL_PROMPT_SCENES: CallPromptScene[] = [
  'hold',
  'consult',
  'three_party',
  'transfer',
]

export const DEFAULT_TTS_TEXT: Record<CallPromptScene, string> = {
  hold: '通话已保持，请稍候。',
  consult: '客服正在为您咨询，请稍候。',
  three_party: '正在邀请其他人员加入通话，请稍候。',
  transfer: '正在为您转接，请稍候。',
}
