export type PersonalOutboundTaskOption = {
  id: number
  name: string
  callable_count: number
}

export type PersonalOutboundPhoneOption = {
  id: string
  phone_number: string
}

export type PersonalOutboundGroupOption = {
  id: number
  name: string
  ready_agent_count: number
}

export type PersonalOutboundAudio = {
  id: number
  name: string
  mime_type: string
  size_bytes: number
  duration_ms: number | null
  preview_url: string | null
  created_at: string | null
}

export type PersonalOutboundRecording = {
  recording_type: 'opening' | 'closing'
  audio: PersonalOutboundAudio
  script_text?: string | null
}

export type PersonalAutoOutboundConfig = {
  tasks: PersonalOutboundTaskOption[]
  phone_numbers: PersonalOutboundPhoneOption[]
  fallback_groups: PersonalOutboundGroupOption[]
  recordings: Partial<Record<'opening' | 'closing', PersonalOutboundRecording>>
  has_enabled_prescreen_intents: boolean
}

export type PersonalAutoOutboundStart = {
  task_id: number
  outbound_phone_number_id: string
  fallback_group_id: number | null
  configured_concurrency: number
}

export type PersonalAutoOutboundSession = {
  id: number
  task_id: number
  outbound_phone_number_id: string
  fallback_group_id: number | null
  opening_audio_asset_id: number
  closing_audio_asset_id: number
  opening_script_text?: string | null
  configured_concurrency: number
  effective_concurrency: number
  status: string
  pause_reason: string | null
  started_at: string
  paused_at: string | null
  stopping_at: string | null
  stopped_at: string | null
  created_at: string
  updated_at: string
}

export type PersonalAutoOutboundMetrics = {
  ringing_current: number
  ringing_total: number
  screening_current: number
  screening_total: number
  human_current: number
  human_total: number
  filtered_current: number
  filtered_total: number
}

export type PersonalAutoOutboundCall = {
  id: number
  target_id: number
  call_record_id: number | null
  target_name?: string | null
  phone_number: string
  stage: string
  prescreen_result: string | null
  intent_key: string | null
  similarity: number | null
  degraded_reason: string | null
  assigned_agent_id: number | null
  assignment_type: string | null
  hangup_reason: string | null
  last_utterance?: string | null
  started_at: string
  answered_at: string | null
  ended_at: string | null
}

export type PersonalAutoOutboundSessionEnvelope = {
  session: PersonalAutoOutboundSession | null
  metrics: PersonalAutoOutboundMetrics
  calls: PersonalAutoOutboundCall[]
  gate_reason: string | null
}
