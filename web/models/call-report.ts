export type TrendType = 'half_hour' | 'hour' | 'day' | 'week' | 'month'

export type CallMetricKey =
  | 'total_calls'
  | 'inbound_calls'
  | 'answered_inbound_calls'
  | 'outbound_calls'
  | 'answered_outbound_calls'
  | 'avg_inbound_talk_seconds'
  | 'avg_outbound_talk_seconds'

export type CallOverviewMetrics = {
  total_calls: number
  inbound_calls: number
  answered_inbound_calls: number
  outbound_calls: number
  answered_outbound_calls: number
  avg_inbound_talk_seconds: number | null
  avg_outbound_talk_seconds: number | null
}

export type CallOverviewResponse = CallOverviewMetrics & {
  as_of: string
}

export type CallTrendBucket = {
  label: string
  bucket_start: string
  bucket_end: string
  metrics: CallOverviewMetrics
}

export type CallTrendResponse = {
  trend: TrendType
  buckets: CallTrendBucket[]
  as_of: string
}

export type CallEmployeeBrief = {
  id: number
  name: string
  username: string | null
  display_name: string | null
  email: string | null
  avatar: string | null
  is_active: boolean
}

export type CallEmployeeOverviewRow = {
  employee: CallEmployeeBrief
  metrics: CallOverviewMetrics
}

export type CallEmployeesListResponse = {
  items: CallEmployeeOverviewRow[]
  total: number
  page: number
  per_page: number
  pages: number
  sort: CallEmployeeSortField
  order: SortOrder
  as_of: string
}

export type CallEmployeeSortField =
  | 'total_calls'
  | 'inbound_calls'
  | 'answered_inbound_calls'
  | 'outbound_calls'
  | 'answered_outbound_calls'
  | 'avg_inbound_talk_seconds'
  | 'avg_outbound_talk_seconds'
  | 'name'

export type SortOrder = 'asc' | 'desc'
