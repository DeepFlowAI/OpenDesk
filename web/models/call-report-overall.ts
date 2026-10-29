import type { TrendType } from '@/models/call-report'

export type CallMetricFormat = 'integer' | 'duration_seconds' | 'percent'
export type CallMetricLevel = 'primary' | 'auxiliary'

export type CallOverallMetric = {
  key: string
  value: number | null
  format: CallMetricFormat
  level: CallMetricLevel
  group: string
  available: boolean
}

export type CallDistributionSlice = {
  key: string
  label: string
  value: number
}

export type CallMetricDistribution = {
  key: string
  group: string
  total: number
  slices: CallDistributionSlice[]
}

export type CallReportDataQuality = {
  pending: number
  incomplete: number
  failed: number
  satisfaction_pending: number
}

export type CallReportCoverage = {
  effective_at: string
  requested_start: string
  requested_end: string
  actual_start: string | null
  actual_end: string | null
  truncated: boolean
  status: 'available' | 'partial' | 'unavailable'
}

export type CallOverallSummaryResponse = {
  metrics: CallOverallMetric[]
  distributions: CallMetricDistribution[]
  data_quality: CallReportDataQuality
  coverage: CallReportCoverage
  as_of: string
}

export type CallTrendMetricValue = {
  key: string
  value: number | null
  format: CallMetricFormat
}

export type CallOverallTrendBucket = {
  label: string
  bucket_start: string
  bucket_end: string
  metrics: CallTrendMetricValue[]
}

export type CallOverallTrendResponse = {
  trend: TrendType
  group: string
  metrics: CallOverallMetric[]
  buckets: CallOverallTrendBucket[]
  coverage: CallReportCoverage
  as_of: string
}
