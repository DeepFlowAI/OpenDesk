import type { TrendType } from '@/models/session-report'

// Grouped overall report framework (flat metric list; frontend groups by `group`).

export type MetricFormat = 'integer' | 'duration_seconds' | 'percent'
export type MetricLevel = 'primary' | 'auxiliary'

export type MetricResult = {
  key: string
  value: number | null
  format: MetricFormat
  level: MetricLevel
  group: string
  available: boolean
}

export type OverallSummaryResponse = {
  metrics: MetricResult[]
  distributions: MetricDistribution[]
  as_of: string
}

export type MetricDistributionSlice = {
  key: string
  label: string
  value: number
}

export type MetricDistribution = {
  key: string
  group: string
  total: number
  slices: MetricDistributionSlice[]
}

export type OverallTrendMetricValue = {
  key: string
  value: number | null
  format: MetricFormat
}

export type OverallTrendBucket = {
  label: string
  bucket_start: string
  bucket_end: string
  metrics: OverallTrendMetricValue[]
}

// Descriptor of a trendable metric of the selected group (no per-bucket value).
export type OverallTrendDescriptor = {
  key: string
  value: number | null
  format: MetricFormat
  level: MetricLevel
  group: string
}

export type OverallTrendResponse = {
  trend: TrendType
  group: string
  metrics: OverallTrendDescriptor[]
  buckets: OverallTrendBucket[]
  as_of: string
}

export type OverallExportParams = {
  start: string
  end: string
  trend: TrendType
}
