export type WorkspaceChatPreferences = {
  auxiliary_panel_width?: number
  composer_input_height?: number
}

export type UserPreferences = {
  workspace_chat?: WorkspaceChatPreferences
  [key: string]: unknown
}

export type LoginPayload = {
  tenant: string
  username: string
  password: string
}

export type UserInfo = {
  id: number
  username: string
  name: string
  display_name: string | null
  avatar: string | null
  roles: string[]
  tenant_id: number
  role_ids: number[]
  permissions: string[]
  data_scopes: Record<string, 'all' | 'group' | 'self'>
  is_super_admin: boolean
  group_ids: number[]
  preferences: UserPreferences
}

export type LoginResponse = {
  access_token: string
  token_type: string
  user: UserInfo
}
