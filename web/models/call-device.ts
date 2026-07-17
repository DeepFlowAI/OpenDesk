export type CallDeviceType = 'webrtc' | 'sip_phone'

export interface AgentCallDevice {
  device_type: CallDeviceType
  name: string
  available: boolean
  unavailable_reason: string | null
  extension_number?: string | null
  registration_status?: 'registered' | 'unregistered' | null
}

export interface AgentDeviceListResponse {
  items: AgentCallDevice[]
}

export interface AgentCurrentDevice {
  device_type: CallDeviceType | null
}
