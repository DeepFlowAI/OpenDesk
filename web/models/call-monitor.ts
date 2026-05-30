import type { EmployeeBrief } from '@/models/session-report'
import type { AgentStatus } from '@/models/call-center'

export type CallMonitorToday = {
  range_label: string
  total_calls: number
  inbound_calls: number
  answered_inbound_calls: number
  outbound_calls: number
  answered_outbound_calls: number
}

export type CallMonitorEmployeeRow = {
  employee: EmployeeBrief
  call_center_status: AgentStatus
  answered_inbound_calls: number
  outbound_calls: number
  answered_outbound_calls: number
}

export type CallMonitorResponse = {
  today: CallMonitorToday
  employees: CallMonitorEmployeeRow[]
  as_of: string
}
