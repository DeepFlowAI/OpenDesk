import type { PaginatedResponse } from '@/models/common'
import type { VoiceFlowGraph } from '@/models/voice-flow-graph'

export type VoiceFlow = {
  id: number
  name: string
  description: string | null
  enabled: boolean
  current_version_no: number | null
  graph_json: VoiceFlowGraph | null
  created_at: string | null
  updated_at: string | null
}

export type VoiceFlowListItem = {
  id: number
  name: string
  description: string | null
  enabled: boolean
  current_version_no: number | null
  created_at: string | null
  updated_at: string | null
}

export type VoiceFlowSelectItem = { id: number; name: string }

export type VoiceFlowSelectResponse = { items: VoiceFlowSelectItem[] }

export type VoiceFlowListResponse = PaginatedResponse<VoiceFlowListItem>

export type CreateVoiceFlowPayload = {
  name: string
  description?: string | null
  enabled?: boolean
}

export type UpdateVoiceFlowPayload = {
  name?: string
  description?: string | null
  enabled?: boolean
  graph_json?: VoiceFlowGraph
}

export type GraphError = {
  node_id: string | null
  field: string | null
  code: string
  message: string
}

export type GraphValidationResult = {
  ok: boolean
  errors: GraphError[]
}

export type SystemVariable = {
  name: string
  display_name_zh: string
  display_name_en: string
  value_type: 'text' | 'time'
  description_zh: string
  description_en: string
  sort_order: number
}

export type AudioAsset = {
  id: number
  name: string
  mime_type: string
  size_bytes: number
  duration_ms: number | null
  preview_url: string | null
  created_at: string | null
}
