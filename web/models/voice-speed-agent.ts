/**
 * VoiceSpeed agent types — mirrors the backend Pydantic schemas
 * `VoiceSpeedAgentSummary` / `VoiceSpeedAgentListResponse` defined in
 * server/app/schemas/open_agent_settings.py.
 *
 * Only the four low-coupling fields (id/name/description/status) are exposed;
 * voice/model/prompt all live inside VoiceSpeed and are never read here.
 */
export type VoiceSpeedAgent = {
  id: string
  name: string
  description: string | null
  status: string
}

export type VoiceSpeedAgentListResponse = {
  // `configured` is false when the tenant has no VoiceSpeed base_url / api_key
  // bound yet, so the UI can show a "not configured" state instead of an error.
  configured: boolean
  items: VoiceSpeedAgent[]
}
