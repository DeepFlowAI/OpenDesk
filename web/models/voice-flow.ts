import type { PaginatedResponse } from '@/models/common'

export type VoiceFlow = {
  id: number
  name: string
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export type VoiceFlowListItem = VoiceFlow

export type VoiceFlowSelectItem = { id: number; name: string }

export type VoiceFlowSelectResponse = { items: VoiceFlowSelectItem[] }

export type VoiceFlowListResponse = PaginatedResponse<VoiceFlowListItem>

export type CreateVoiceFlowPayload = { name: string; enabled: boolean }

export type UpdateVoiceFlowPayload = CreateVoiceFlowPayload
