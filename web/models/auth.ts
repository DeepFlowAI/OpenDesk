export type LoginPayload = {
  tenant: string
  username: string
  password: string
}

export type UserInfo = {
  id: number
  username: string
  display_name: string | null
  avatar: string | null
  roles: string[]
  tenant_id: number
  role_ids: number[]
  permissions: string[]
  data_scopes: Record<string, 'all' | 'group' | 'self'>
  is_super_admin: boolean
  group_ids: number[]
}

export type LoginResponse = {
  access_token: string
  token_type: string
  user: UserInfo
}
