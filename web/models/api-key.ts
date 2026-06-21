export type ApiKeyRecord = {
  id: number
  name: string
  masked_key: string
  key_version: number
  is_active: boolean
  disabled_at: string | null
  last_used_at: string | null
  created_at: string | null
  updated_at: string | null
}

export type CreateApiKeyPayload = {
  name: string
}

export type ApiKeySecretResponse = {
  record: ApiKeyRecord
  api_key: string
}
