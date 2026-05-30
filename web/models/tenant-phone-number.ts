import type { PaginatedResponse } from './common'

export type PhoneCallType = 'inbound' | 'outbound'

export interface OutboundTimeSlot {
  start: string
  end: string
}

export interface TenantPhoneNumber {
  id: string
  phone_number: string
  call_types: PhoneCallType[]
  tags: string[]
  outbound_time_slots: OutboundTimeSlot[]
  created_at: string | null
  updated_at: string | null
}

export type TenantPhoneNumberListResponse = PaginatedResponse<TenantPhoneNumber>

export interface UpdateTenantPhoneNumberTagsPayload {
  tags: string[]
}
