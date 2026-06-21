export type EmployeeGroupMember = {
  employee_id: number
  name?: string | null
  username: string
  display_name: string | null
}

export type EmployeeGroup = {
  id: number
  name: string
  description: string | null
  member_count: number
  members: EmployeeGroupMember[]
  created_at: string
  updated_at: string
}

export type EmployeeGroupListItem = {
  id: number
  name: string
  description: string | null
  member_count: number
  created_at: string
  updated_at: string
}

export type CreateEmployeeGroupPayload = {
  name: string
  description?: string | null
  member_ids: number[]
}

export type UpdateEmployeeGroupPayload = CreateEmployeeGroupPayload

export type UserListItem = {
  id: number
  name?: string | null
  username: string
  display_name: string | null
}
