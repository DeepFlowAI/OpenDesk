import type { MetricKey, TrendType } from '@/models/session-report'

export const TREND_TYPES: TrendType[] = ['half_hour', 'hour', 'day', 'week', 'month']

export const BASIC_METRIC_KEYS: MetricKey[] = [
  'session_count',
  'message_count',
  'user_message_count',
  'agent_message_count',
  'avg_duration_seconds',
]

export const BUSINESS_METRIC_KEYS: MetricKey[] = [
  'bot_session_count',
  'bot_handoff_count',
  'queued_session_count',
  'avg_queue_duration_seconds',
  'offline_message_count',
]

export const METRIC_KEYS: MetricKey[] = [...BASIC_METRIC_KEYS, ...BUSINESS_METRIC_KEYS]

// Reception-segment metrics are shown as overview/employee supplements only;
// they are intentionally kept out of MetricKey / the trend metric selector.
export type ReceptionMetricKey =
  | 'reception_segment_count'
  | 'reception_participated_session_count'
  | 'reception_final_session_count'
  | 'reception_transfer_in_count'
  | 'reception_transfer_out_count'

export const RECEPTION_METRIC_KEYS: ReceptionMetricKey[] = [
  'reception_segment_count',
  'reception_participated_session_count',
  'reception_final_session_count',
  'reception_transfer_in_count',
  'reception_transfer_out_count',
]

export const receptionMetricLabelKey: Record<ReceptionMetricKey, string> = {
  reception_segment_count: 'ws.records.sessionReports.overview.receptionSegmentCount',
  reception_participated_session_count: 'ws.records.sessionReports.overview.receptionParticipatedSessionCount',
  reception_final_session_count: 'ws.records.sessionReports.overview.receptionFinalSessionCount',
  reception_transfer_in_count: 'ws.records.sessionReports.overview.receptionTransferInCount',
  reception_transfer_out_count: 'ws.records.sessionReports.overview.receptionTransferOutCount',
}

export const receptionMetricTooltipKey: Partial<Record<ReceptionMetricKey, string>> = {
  reception_segment_count: 'ws.records.sessionReports.tooltip.receptionSegmentCount',
  reception_final_session_count: 'ws.records.sessionReports.tooltip.receptionFinalSessionCount',
}

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
  bot_session_count: 'ws.records.sessionReports.overview.botSessionCount',
  bot_handoff_count: 'ws.records.sessionReports.overview.botHandoffCount',
  queued_session_count: 'ws.records.sessionReports.overview.queuedSessionCount',
  avg_queue_duration_seconds: 'ws.records.sessionReports.overview.avgQueueDuration',
  offline_message_count: 'ws.records.sessionReports.overview.offlineMessageCount',
}

export const metricTooltipKey: Partial<Record<MetricKey, string>> = {
  bot_session_count: 'ws.records.sessionReports.tooltip.botSessionCount',
  bot_handoff_count: 'ws.records.sessionReports.tooltip.botHandoffCount',
  queued_session_count: 'ws.records.sessionReports.tooltip.queuedSessionCount',
  offline_message_count: 'ws.records.sessionReports.tooltip.offlineMessageCount',
}

export function isDurationMetric(metric: MetricKey): boolean {
  return metric === 'avg_duration_seconds' || metric === 'avg_queue_duration_seconds'
}

export function visibleMetricKeys(options: {
  includeBusinessMetrics: boolean
  canViewOfflineMessages: boolean
}): MetricKey[] {
  if (!options.includeBusinessMetrics) return BASIC_METRIC_KEYS
  return [
    ...BASIC_METRIC_KEYS,
    ...BUSINESS_METRIC_KEYS.filter((key) => (
      key !== 'offline_message_count' || options.canViewOfflineMessages
    )),
  ]
}
