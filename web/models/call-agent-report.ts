import type { SortOrder, TrendType } from '@/models/call-report'
import type {
  CallMetricDistribution,
  CallOverallMetric,
  CallOverallTrendBucket,
  CallReportCoverage,
} from '@/models/call-report-overall'

export type CallAgentStatus = 'active' | 'inactive' | 'deleted'

export type CallAgentBrief = {
  id: number
  name: string
  username: string | null
  display_name: string | null
  email: string | null
  avatar: string | null
  is_active: boolean
  status: CallAgentStatus
}

export type CallAgentOverviewMetrics = {
  participated_call_count: number
  handled_call_count: number
  reception_segment_count: number
  inbound_handled_call_count: number
  outbound_attempt_count: number
  outbound_customer_answered_count: number
  outbound_handled_call_count: number
  transfer_in_segment_count: number
  offered_call_count: number
  offer_attempt_count: number
  offer_accepted_count: number
  offer_accept_rate: number | null
  offer_rejected_count: number
  offer_timeout_count: number
  offer_timeout_rate: number | null
  avg_offer_response_seconds: number | null
  total_talk_seconds: number | null
  avg_talk_seconds: number | null
  held_segment_count: number
  total_hold_seconds: number | null
  avg_hold_seconds: number | null
  total_after_call_work_seconds: number | null
  avg_after_call_work_seconds: number | null
  avg_handle_seconds: number | null
  transfer_attempt_count: number
  transfer_completed_count: number
  transfer_success_rate: number | null
  transfer_failed_count: number
  consult_attempt_count: number
  consult_connected_count: number
  consult_success_rate: number | null
  conference_join_count: number
}

export type CallAgentOverviewRow = { employee: CallAgentBrief; metrics: CallAgentOverviewMetrics }

export type CallAgentDataQuality = {
  processing: number
  reception_incomplete: number
  offer_incomplete: number
  after_call_work_incomplete: number
  failed: number
}

export type CallAgentSortField = keyof CallAgentOverviewMetrics | 'name' | 'status'

export type CallAgentListResponse = {
  items: CallAgentOverviewRow[]
  total: number
  page: number
  per_page: number
  pages: number
  sort: CallAgentSortField
  order: SortOrder
  data_quality: CallAgentDataQuality
  coverage: CallReportCoverage
  as_of: string
}

export type CallAgentSummaryResponse = {
  employee: CallAgentBrief
  group_names: string[]
  metrics: CallOverallMetric[]
  distributions: CallMetricDistribution[]
  data_quality: CallAgentDataQuality
  coverage: CallReportCoverage
  as_of: string
}

export type CallAgentTrendResponse = {
  trend: TrendType
  group: string
  metrics: CallOverallMetric[]
  buckets: CallOverallTrendBucket[]
  coverage: CallReportCoverage
  as_of: string
}
