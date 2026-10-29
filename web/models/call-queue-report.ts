import type { SortOrder, TrendType } from '@/models/call-report'
import type {
  CallMetricDistribution,
  CallOverallMetric,
  CallOverallTrendBucket,
  CallReportCoverage,
} from '@/models/call-report-overall'

export type CallQueueType = 'employee_group' | 'employee'
export type CallQueueTypeFilter = CallQueueType | 'all'
export type CallQueueStatus = 'active' | 'inactive' | 'deleted'

export type CallQueueBrief = {
  queue_type: CallQueueType
  queue_id: number
  name: string
  status: CallQueueStatus
}

export type CallQueueOverviewMetrics = {
  queue_call_count: number
  queue_entry_count: number
  first_queue_entry_count: number
  transfer_in_entry_count: number
  queue_answered_count: number
  queue_answer_rate: number | null
  queue_abandoned_count: number
  queue_abandon_rate: number | null
  queue_short_abandon_count: number
  queue_short_abandon_rate: number | null
  queue_timeout_count: number
  queue_transfer_out_count: number
  avg_answer_wait_seconds: number | null
  avg_abandon_wait_seconds: number | null
  avg_queue_wait_seconds: number | null
  max_queue_wait_seconds: number | null
  queue_service_level_20s: number | null
  offered_call_count: number
  offer_attempt_count: number
  offer_accepted_count: number
  offer_rejected_count: number
  offer_timeout_count: number
  offer_accept_rate: number | null
}

export type CallQueueOverviewRow = {
  queue: CallQueueBrief
  metrics: CallQueueOverviewMetrics
}

export type CallQueueDataQuality = {
  pending: number
  incomplete: number
  failed: number
}

export type CallQueueSortField = keyof CallQueueOverviewMetrics | 'name' | 'queue_type' | 'status'

export type CallQueueListResponse = {
  items: CallQueueOverviewRow[]
  total: number
  page: number
  per_page: number
  pages: number
  sort: CallQueueSortField
  order: SortOrder
  data_quality: CallQueueDataQuality
  coverage: CallReportCoverage
  as_of: string
}

export type CallQueueSummaryResponse = {
  queue: CallQueueBrief
  metrics: CallOverallMetric[]
  distributions: CallMetricDistribution[]
  data_quality: CallQueueDataQuality
  coverage: CallReportCoverage
  as_of: string
}

export type CallQueueTrendResponse = {
  trend: TrendType
  group: string
  metrics: CallOverallMetric[]
  buckets: CallOverallTrendBucket[]
  coverage: CallReportCoverage
  as_of: string
}
