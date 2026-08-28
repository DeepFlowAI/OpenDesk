export type SystemSettings = {
  default_language: string
  default_timezone: string
  organization_enabled: boolean
  bridge_asr_enabled: boolean
  call_wrapup_seconds: number
}

export type UpdateSystemSettingsPayload = {
  default_language: string
  default_timezone: string
}

export type UpdateOrganizationSettingsPayload = {
  organization_enabled: boolean
}

export type UpdateCallTranscriptionPayload = {
  enabled: boolean
}

export type UpdateCallWrapupPayload = {
  seconds: number
}
