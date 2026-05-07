export type SystemSettings = {
  default_language: string
  default_timezone: string
  organization_enabled: boolean
}

export type UpdateSystemSettingsPayload = {
  default_language: string
  default_timezone: string
}

export type UpdateOrganizationSettingsPayload = {
  organization_enabled: boolean
}
