export type TrendType = 'half_hour' | 'hour' | 'day' | 'week' | 'month'

export type MetricKey =
  | 'session_count'
  | 'message_count'
  | 'user_message_count'
  | 'agent_message_count'
  | 'avg_duration_seconds'
  | 'bot_session_count'
  | 'bot_handoff_count'
  | 'queued_session_count'
  | 'avg_queue_duration_seconds'
  | 'offline_message_count'

export type OverviewMetrics = {
  session_count: number
  message_count: number
  user_message_count: number
  agent_message_count: number
  avg_duration_seconds: number | null
  bot_session_count: number
  bot_handoff_count: number
  queued_session_count: number
  avg_queue_duration_seconds: number | null
  offline_message_count: number | null
  can_view_offline_messages: boolean
  reception_segment_count: number
  reception_participated_session_count: number
  reception_final_session_count: number
  reception_transfer_in_count: number
  reception_transfer_out_count: number
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

export type EmployeeDetailResponse = {
  employee: EmployeeBrief
  metrics: OverviewMetrics
  as_of: string
}

export type EmployeesListResponse = {
  items: EmployeeOverviewRow[]
  total: number
  page: number
  per_page: number
  pages: number
  as_of: string
}

export type QueueType = 'employee_group' | 'employee'
export type QueueStatus = 'active' | 'inactive' | 'deleted'
export type QueueMetricGroup = 'queue_access' | 'human_messages' | 'service_efficiency'
export type QueueMetricFormat = 'integer' | 'duration_seconds' | 'percent'
export type QueueMetricLevel = 'primary' | 'auxiliary'

export type QueueBrief = {
  queue_type: QueueType
  queue_id: number
  name: string
  status: QueueStatus
}

export type QueueReportMetrics = {
  queued_session_count: number
  assigned_queue_session_count: number
  unassigned_queue_session_count: number
  queue_assign_rate: number | null
  avg_queue_duration_seconds: number | null
  max_queue_duration_seconds: number | null
  final_session_count: number
  effective_session_count: number
  user_message_count: number
  agent_message_count: number
  unreplied_session_count: number
  visitor_silent_session_count: number
  avg_first_human_response_seconds: number | null
  avg_agent_response_seconds: number | null
  avg_human_session_duration_seconds: number | null
}

export type QueueOverviewRow = {
  queue: QueueBrief
  metrics: QueueReportMetrics
}

export type QueueListResponse = {
  items: QueueOverviewRow[]
  total: number
  page: number
  per_page: number
  pages: number
  sort: QueueSortField
  order: SortOrder
  as_of: string
}

export type QueueDetailResponse = {
  queue: QueueBrief
  metrics: QueueReportMetrics
  as_of: string
}

export type QueueMetricKey = keyof QueueReportMetrics

export type QueueTrendDescriptor = {
  key: QueueMetricKey
  value: number | null
  format: QueueMetricFormat
  level: QueueMetricLevel
  group: QueueMetricGroup
}

export type QueueTrendMetricValue = {
  key: QueueMetricKey
  value: number | null
  format: QueueMetricFormat
}

export type QueueTrendBucket = {
  label: string
  bucket_start: string
  bucket_end: string
  metrics: QueueTrendMetricValue[]
}

export type QueueTrendResponse = {
  trend: TrendType
  group: QueueMetricGroup
  metrics: QueueTrendDescriptor[]
  buckets: QueueTrendBucket[]
  as_of: string
}

export type EmployeeSortField =
  | 'session_count'
  | 'message_count'
  | 'user_message_count'
  | 'agent_message_count'
  | 'avg_duration_seconds'
  | 'reception_segment_count'
  | 'reception_participated_session_count'
  | 'reception_final_session_count'
  | 'reception_transfer_in_count'
  | 'reception_transfer_out_count'
  | 'name'

export type QueueSortField =
  | 'name'
  | 'queue_type'
  | 'status'
  | QueueMetricKey

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

export type QueueReportExportParams = {
  scope: 'list' | 'detail'
  start: string
  end: string
  trend?: TrendType
  group?: QueueMetricGroup
  queue_type?: QueueType
  queue_id?: number
  q?: string
  sort?: QueueSortField
  order?: SortOrder
}
