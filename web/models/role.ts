export type DataScopeValue = 'all' | 'group' | 'self'

export type PermissionNode = {
  key: string
  name: string
  name_en: string
  type: 'switch' | 'menu' | 'action' | 'manage' | string
  requires?: string | null
  data_scope_resource?: string | null
}

export type PermissionModule = {
  key: string
  name: string
  name_en: string
  permissions: PermissionNode[]
}

export type PermissionTab = {
  key: string
  name: string
  name_en: string
  modules: PermissionModule[]
}

export type PermissionTreeResponse = {
  tabs: PermissionTab[]
  data_scope_options: DataScopeValue[]
}

export type Role = {
  id: number
  tenant_id: number
  key: string | null
  name: string
  description: string | null
  is_system: boolean
  is_active: boolean
  permissions: string[]
  data_scopes: Record<string, DataScopeValue>
  member_count: number
  created_at: string | null
  updated_at: string | null
}

export type RoleOption = {
  id: number
  key: string | null
  name: string
  description: string | null
  is_system: boolean
  is_active: boolean
  permissions: string[]
}

export type RolePayload = {
  name: string
  description?: string | null
  is_active?: boolean
  permissions: string[]
  data_scopes: Record<string, DataScopeValue>
}
