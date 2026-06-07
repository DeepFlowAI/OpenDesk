export type Employee = {
  id: number
  name: string
  nickname: string | null
  job_number: string | null
  username: string
  email: string | null
  phone: string | null
  avatar: string | null
  roles: string[]
  role_ids?: number[]
  role_assignments?: EmployeeRoleAssignment[]
  is_active: boolean
  max_concurrent: number
  default_language: string
  is_super_admin: boolean
  group_ids?: number[]
  created_at: string
  updated_at: string
}

export type EmployeeRoleAssignment = {
  id: number
  key: string | null
  name: string
  is_system: boolean
  is_active: boolean
  permissions: string[]
}

export type CreateEmployeePayload = {
  name: string
  nickname?: string | null
  job_number?: string | null
  username: string
  email: string
  phone?: string | null
  password: string
  avatar?: string | null
  roles?: string[]
  role_ids?: number[]
  max_concurrent?: number
  default_language?: string
  group_ids?: number[]
}

export type UpdateEmployeePayload = {
  name?: string
  nickname?: string | null
  job_number?: string | null
  username?: string
  email?: string
  phone?: string | null
  password?: string
  avatar?: string | null
  roles?: string[]
  role_ids?: number[]
  max_concurrent?: number
  default_language?: string
  group_ids?: number[]
}

export type EmployeeStatusPayload = {
  is_active: boolean
}
