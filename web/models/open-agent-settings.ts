export type OpenAgentSettings = {
  base_url: string | null
  has_api_key: boolean
  updated_at: string | null
}

export type UpdateOpenAgentSettingsPayload = {
  base_url: string
  api_key?: string
}

export type TestOpenAgentConnectionPayload = {
  base_url: string
  api_key?: string
}

export type TestOpenAgentConnectionResponse = {
  ok: boolean
  message: string
}

export type OpenAgentAgent = {
  id: number
  name: string
  description: string | null
  status: 'active' | 'inactive' | string
}

export type OpenAgentAgentListResponse = {
  items: OpenAgentAgent[]
  total: number
  page: number
  per_page: number
  pages: number
}
