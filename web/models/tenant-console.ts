export type ConsoleTenantStatus = 'enabled' | 'disabled'

export type ConsoleTenant = {
  id: string
  slug: string | null
  name: string
  remark: string | null
  status: ConsoleTenantStatus
  admin_username: string | null
  created_at: string | null
  updated_at: string | null
}

export type ConsoleTenantCreatePayload = {
  name: string
  slug?: string | null
  remark?: string | null
  admin_username: string
  admin_password: string
}

export type ConsoleTenantUpdatePayload = {
  name?: string
  slug?: string | null
  remark?: string | null
  admin_username?: string
  admin_password?: string
}

export type TrunkType = 'inbound' | 'outbound'
export type TrunkStatus = 'enabled' | 'disabled'

export type PeerEndpoint = {
  ip: string
  port: number
}

export type SipTrunk = {
  id: string
  supplier_name: string
  trunk_name: string
  trunk_types: TrunkType[]
  remark: string | null
  status: TrunkStatus
  peer_endpoints: PeerEndpoint[]
  peer_endpoint_count: number
  created_at: string
  updated_at: string
}

export type SipTrunkPayload = {
  supplier_name: string
  trunk_name: string
  trunk_types: TrunkType[]
  remark: string | null
  status: TrunkStatus
  peer_endpoints: PeerEndpoint[]
}

export type SipTrunkOption = {
  id: string
  trunk_name: string
  supplier_name: string
  status: TrunkStatus
  trunk_types: TrunkType[]
}

export type SipTrunkListParams = {
  page?: number
  per_page?: number
  q?: string
  status?: TrunkStatus | ''
}

export type PhoneStatus = 'available' | 'assigned' | 'disabled'
export type PhoneCallType = 'inbound' | 'outbound'

export type OutboundTimeSlot = {
  start: string
  end: string
}

export type PhoneNumber = {
  id: string
  phone_number: string
  call_types: PhoneCallType[]
  trunk_id: string | null
  trunk_name: string | null
  supplier_name: string | null
  tenant_id: string | null
  tenant_name: string | null
  tenant_status: string | null
  status: PhoneStatus
  remark: string | null
  concurrency: number | null
  called_number_prefix: string | null
  outbound_time_slots: OutboundTimeSlot[]
  created_at: string
  updated_at: string
}

export type PhoneNumberCreatePayload = {
  phone_number: string
  call_types: PhoneCallType[]
  trunk_id: string | null
  tenant_id: string | null
  status: PhoneStatus
  remark: string | null
  concurrency: number | null
  called_number_prefix: string | null
  outbound_time_slots: OutboundTimeSlot[]
}

/** Omitted keys are left unchanged; `null` clears a binding. */
export type PhoneNumberUpdatePayload = Partial<Omit<PhoneNumberCreatePayload, 'phone_number'>>

export type PhoneNumberBatchPayload = {
  ids: string[]
  call_types?: PhoneCallType[]
  trunk_id?: string | null
  tenant_id?: string | null
  status?: PhoneStatus
}

export type PhoneNumberBatchResult = {
  success_count: number
  fail_count: number
  failures: { id: string; phone_number: string | null; reason: string }[]
}

export type PhoneNumberListParams = {
  page?: number
  per_page?: number
  q?: string
  trunk_id?: string
  tenant_id?: string
  status?: PhoneStatus | ''
}

export type ConsoleLoginResponse = {
  access_token: string
  token_type: string
  expires_in: number
  username: string
}
