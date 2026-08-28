export type EmbeddedCallIntegration = {
  public_id: string
  name: string
  integration_key: string
  allowed_origins: string[]
  is_enabled: boolean
  secret_last_four: string
  secret_rotated_at: string
  previous_secret_last_four: string | null
  previous_secret_expires_at: string | null
  last_used_at: string | null
  last_success_at: string | null
  last_failure_at: string | null
  last_error_code: string | null
  created_at: string
  updated_at: string
}

export type EmbeddedCallIntegrationList = {
  items: EmbeddedCallIntegration[]
  total: number
}

export type EmbeddedCallIntegrationPayload = {
  name: string
  allowed_origins: string[]
  is_enabled: boolean
}

export type EmbeddedCallIntegrationSecretResult = {
  integration: EmbeddedCallIntegration
  server_secret: string
}

export type EmbedSession = {
  access_token: string
  token_type: string
  expires_in: number
  integration_key: string
  agent: {
    name: string
    display_name: string | null
    default_language: string
    permissions: string[]
  }
}

export type EmbeddedExternalContext = {
  record_type?: string
  record_id?: string
  display_name?: string
  attributes?: Record<string, string>
}

export type EmbeddedDialPayload = {
  number: string
  outboundNumberId?: string
  externalContext?: EmbeddedExternalContext
  customBusinessInfo?: string
  idempotencyKey?: string
}

export type EmbeddedDialCommand = {
  command_id: string
  call_id: string | null
  status: string
}

export type EmbeddedControlLease = {
  is_owner: boolean
  owner_instance_id: string | null
  owner_surface?: string | null
  lease_token: string | null
  expires_in: number
}
