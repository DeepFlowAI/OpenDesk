export type TrendType = 'half_hour' | 'hour' | 'day' | 'week' | 'month'

export type MetricKey =
  | 'session_count'
  | 'message_count'
  | 'user_message_count'
  | 'agent_message_count'
  | 'avg_duration_seconds'

export type OverviewMetrics = {
  session_count: number
  message_count: number
  user_message_count: number
  agent_message_count: number
  avg_duration_seconds: number | null
}

export type OverviewResponse = OverviewMetrics & {
  as_of: string
}

export type TrendBucket = {
  label: string
  bucket_start: string
  bucket_end: string
  metrics: OverviewMetrics
}

export type TrendResponse = {
  trend: TrendType
  buckets: TrendBucket[]
  as_of: string
}

export type EmployeeBrief = {
  id: number
  name: string
  username: string | null
  display_name: string | null
  email: string | null
  avatar: string | null
  is_active: boolean
}

export type EmployeeOverviewRow = {
  employee: EmployeeBrief
  metrics: OverviewMetrics
}

export type EmployeesListResponse = {
  items: EmployeeOverviewRow[]
  total: number
  page: number
  per_page: number
  pages: number
  as_of: string
}

export type EmployeeSortField =
  | 'session_count'
  | 'message_count'
  | 'user_message_count'
  | 'agent_message_count'
  | 'avg_duration_seconds'
  | 'name'

export type SortOrder = 'asc' | 'desc'

export type SessionReportExportScope = 'overall' | 'employees' | 'employee'

export type SessionReportExportParams = {
  scope: SessionReportExportScope
  start: string
  end: string
  trend?: TrendType
  employee_id?: number
  q?: string
  sort?: EmployeeSortField
  order?: SortOrder
}
