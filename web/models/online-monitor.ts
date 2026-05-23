import type { EmployeeBrief } from '@/models/session-report'

export type OnlineStatus = 'online' | 'busy' | 'offline' | 'unknown'

export type TodayOverview = {
  range_label: string
  session_count: number
  avg_duration_seconds: number | null
}

export type EmployeeMonitorRow = {
  employee: EmployeeBrief
  status: OnlineStatus
  current_count: number
  max_concurrent: number
  session_count: number
  avg_duration_seconds: number | null
}

export type OnlineMonitorResponse = {
  today: TodayOverview
  employees: EmployeeMonitorRow[]
  as_of: string
}
