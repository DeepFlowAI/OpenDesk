export type ConditionItem = {
  field_id: number | null
  field_key: string | null
  operator: string
  value: string | number | boolean | null | unknown[]
}

export type ColumnConfigItem = {
  field_id: number | null
  field_key: string | null
  visible: boolean
  sort_order: number
}

export type UserView = {
  id: number
  tenant_id: number
  name: string
  is_enabled: boolean
  sort_order: number
  condition_logic: string
  conditions: ConditionItem[]
  group_field_id: number | null
  custom_columns_enabled: boolean
  columns_config: ColumnConfigItem[]
  created_at: string
  updated_at: string
}

export type CreateUserViewPayload = {
  name: string
  condition_logic?: string
  conditions?: ConditionItem[]
  group_field_id?: number | null
  custom_columns_enabled?: boolean
  columns_config?: ColumnConfigItem[]
}

export type UpdateUserViewPayload = Partial<CreateUserViewPayload>

export type UserViewSortItem = {
  id: number
  sort_order: number
}

export type UserViewSortPayload = {
  items: UserViewSortItem[]
}

export type UserViewTogglePayload = {
  is_enabled: boolean
}
