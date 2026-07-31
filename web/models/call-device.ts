export type CallDeviceType = 'webrtc' | 'sip_phone'

export interface AgentCallDevice {
  device_type: CallDeviceType
  name: string
  available: boolean
  unavailable_reason: string | null
  extension_number?: string | null
  registration_status?: 'registered' | 'unregistered' | null
  status_message?: string | null
  current_occupant_employee_id?: number | null
  current_occupant_name?: string | null
  blocking_agent_name?: string | null
  blocking_agent_count?: number | null
}

export interface AgentDeviceListResponse {
  items: AgentCallDevice[]
}

export interface AgentCurrentDevice {
  device_type: CallDeviceType | null
  available?: boolean
  unavailable_reason?: string | null
  status_message?: string | null
  extension_number?: string | null
  registration_status?: 'registered' | 'unregistered' | null
  current_occupant_employee_id?: number | null
  current_occupant_name?: string | null
  blocking_agent_name?: string | null
  blocking_agent_count?: number | null
}
