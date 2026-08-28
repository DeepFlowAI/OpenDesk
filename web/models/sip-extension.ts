import type { PaginatedResponse } from './common'

export type SipRegistrationStatus = 'registered' | 'unregistered'

export interface SipExtensionBoundEmployee {
  id: number
  name: string
  avatar: string | null
}

export interface SipExtension {
  id: number
  name: string
  extension_number: string
  sip_user_id: string
  auth_account: string
  auth_password_masked: string
  registration_status: SipRegistrationStatus
  last_registered_at: string | null
  is_active: boolean
  disabled_at: string | null
  bound_employee_ids: number[]
  bound_employees: SipExtensionBoundEmployee[]
  current_occupant_employee_id: number | null
  current_occupant: SipExtensionBoundEmployee | null
  created_at: string | null
  updated_at: string | null
}

export type SipExtensionListResponse = PaginatedResponse<SipExtension>

export interface SipExtensionListParams {
  page?: number
  per_page?: number
  keyword?: string
  registration_status?: SipRegistrationStatus
  active_status?: 'active' | 'inactive'
}

export interface BindableEmployee {
  id: number
  name: string
  avatar: string | null
}

export interface CreateSipExtensionPayload {
  name: string
  extension_number: string
  bound_employee_ids?: number[]
}

export interface UpdateSipExtensionPayload {
  name?: string
  bound_employee_ids?: number[]
}

/** Full registration info available to extension administrators. */
export interface SipRegistrationSecret {
  registration_server: string | null
  registration_port: string | null
  transport: string | null
  sip_user_id: string
  auth_account: string
  auth_password: string | null
  auth_password_masked: string
  registration_status: SipRegistrationStatus
}

export interface CreateSipExtensionResponse {
  record: SipExtension
  registration_info: SipRegistrationSecret
}
