import type { CallMetricKey, TrendType } from '@/models/call-report'

export const TREND_TYPES: TrendType[] = ['half_hour', 'hour', 'day', 'week', 'month']

export const CALL_METRIC_KEYS: CallMetricKey[] = [
  'total_calls',
  'inbound_calls',
  'answered_inbound_calls',
  'outbound_calls',
  'answered_outbound_calls',
  'avg_inbound_talk_seconds',
  'avg_outbound_talk_seconds',
]

export const trendTypeLabelKey: Record<TrendType, string> = {
  half_hour: 'ws.records.sessionReports.trend.type.halfHour',
  hour: 'ws.records.sessionReports.trend.type.hour',
  day: 'ws.records.sessionReports.trend.type.day',
  week: 'ws.records.sessionReports.trend.type.week',
  month: 'ws.records.sessionReports.trend.type.month',
}

export const callMetricLabelKey: Record<CallMetricKey, string> = {
  total_calls: 'ws.records.callReports.overview.totalCalls',
  inbound_calls: 'ws.records.callReports.overview.inboundCalls',
  answered_inbound_calls: 'ws.records.callReports.overview.answeredInboundCalls',
  outbound_calls: 'ws.records.callReports.overview.outboundCalls',
  answered_outbound_calls: 'ws.records.callReports.overview.answeredOutboundCalls',
  avg_inbound_talk_seconds: 'ws.records.callReports.overview.avgInboundTalkTime',
  avg_outbound_talk_seconds: 'ws.records.callReports.overview.avgOutboundTalkTime',
}

export function isDurationMetric(metric: CallMetricKey): boolean {
  return metric === 'avg_inbound_talk_seconds' || metric === 'avg_outbound_talk_seconds'
}
