import type { MetricKey, TrendType } from '@/models/session-report'

export const TREND_TYPES: TrendType[] = ['half_hour', 'hour', 'day', 'week', 'month']

export const METRIC_KEYS: MetricKey[] = [
  'session_count',
  'message_count',
  'user_message_count',
  'agent_message_count',
  'avg_duration_seconds',
]

export const trendTypeLabelKey: Record<TrendType, string> = {
  half_hour: 'ws.records.sessionReports.trend.type.halfHour',
  hour: 'ws.records.sessionReports.trend.type.hour',
  day: 'ws.records.sessionReports.trend.type.day',
  week: 'ws.records.sessionReports.trend.type.week',
  month: 'ws.records.sessionReports.trend.type.month',
}

export const metricLabelKey: Record<MetricKey, string> = {
  session_count: 'ws.records.sessionReports.overview.sessionCount',
  message_count: 'ws.records.sessionReports.overview.messageCount',
  user_message_count: 'ws.records.sessionReports.overview.userMessageCount',
  agent_message_count: 'ws.records.sessionReports.overview.agentMessageCount',
  avg_duration_seconds: 'ws.records.sessionReports.overview.avgDuration',
}

export function isDurationMetric(metric: MetricKey): boolean {
  return metric === 'avg_duration_seconds'
}
