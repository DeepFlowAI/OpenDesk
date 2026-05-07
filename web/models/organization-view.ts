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

export type OrganizationView = {
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

export type CreateOrganizationViewPayload = {
  name: string
  condition_logic?: string
  conditions?: ConditionItem[]
  group_field_id?: number | null
  custom_columns_enabled?: boolean
  columns_config?: ColumnConfigItem[]
}

export type UpdateOrganizationViewPayload = Partial<CreateOrganizationViewPayload>

export type OrganizationViewSortItem = {
  id: number
  sort_order: number
}

export type OrganizationViewSortPayload = {
  items: OrganizationViewSortItem[]
}

export type OrganizationViewTogglePayload = {
  is_enabled: boolean
}
