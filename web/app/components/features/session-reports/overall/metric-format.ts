import type { Locale } from '@/context/locale-store'
import type {
  MetricDistribution,
  MetricDistributionSlice,
  MetricFormat,
} from '@/models/session-report-overall'
import { formatDuration } from '@/utils/format-duration'
import { t } from '@/utils/i18n'

// Key → i18n key maps. Adding a metric later = add one entry here + the locale
// strings; the backend already sends the key. Missing keys fall back to the raw
// key so a newly added backend metric never crashes the UI.
export const OVERALL_GROUP_LABEL_KEY: Record<string, string> = {
  session_overall: 'ws.records.sessionReports.overall.group.sessionOverall',
  human_messages: 'ws.records.sessionReports.overall.group.humanMessages',
  queue_access: 'ws.records.sessionReports.overall.group.queueAccess',
  service_efficiency: 'ws.records.sessionReports.overall.group.serviceEfficiency',
  satisfaction: 'ws.records.sessionReports.overall.group.satisfaction',
}

export const OVERALL_METRIC_LABEL_KEY: Record<string, string> = {
  total_session_count: 'ws.records.sessionReports.overall.metric.totalSessionCount',
  pure_bot_session_count: 'ws.records.sessionReports.overall.metric.pureBotSessionCount',
  pure_human_session_count: 'ws.records.sessionReports.overall.metric.pureHumanSessionCount',
  bot_human_session_count: 'ws.records.sessionReports.overall.metric.botHumanSessionCount',
  human_involved_session_count: 'ws.records.sessionReports.overall.metric.humanInvolvedSessionCount',
  effective_session_count: 'ws.records.sessionReports.overall.metric.effectiveSessionCount',
  visitor_message_count: 'ws.records.sessionReports.overall.metric.visitorMessageCount',
  agent_message_count: 'ws.records.sessionReports.overall.metric.agentMessageCount',
  unreplied_session_count: 'ws.records.sessionReports.overall.metric.unrepliedSessionCount',
  visitor_silent_session_count: 'ws.records.sessionReports.overall.metric.visitorSilentSessionCount',
  queued_session_count: 'ws.records.sessionReports.overall.metric.queuedSessionCount',
  assigned_queue_session_count: 'ws.records.sessionReports.overall.metric.assignedQueueSessionCount',
  unassigned_queue_session_count: 'ws.records.sessionReports.overall.metric.unassignedQueueSessionCount',
  avg_queue_duration_seconds: 'ws.records.sessionReports.overall.metric.avgQueueDurationSeconds',
  max_queue_duration_seconds: 'ws.records.sessionReports.overall.metric.maxQueueDurationSeconds',
  queue_assign_rate: 'ws.records.sessionReports.overall.metric.queueAssignRate',
  avg_first_human_response_seconds: 'ws.records.sessionReports.overall.metric.avgFirstHumanResponseSeconds',
  avg_agent_response_seconds: 'ws.records.sessionReports.overall.metric.avgAgentResponseSeconds',
  avg_human_session_duration_seconds: 'ws.records.sessionReports.overall.metric.avgHumanSessionDurationSeconds',
  satisfaction_invitation_count: 'ws.records.sessionReports.overall.metric.satisfactionInvitationCount',
  satisfaction_submission_count: 'ws.records.sessionReports.overall.metric.satisfactionSubmissionCount',
  satisfaction_participation_rate: 'ws.records.sessionReports.overall.metric.satisfactionParticipationRate',
  satisfaction_submission_rate: 'ws.records.sessionReports.overall.metric.satisfactionSubmissionRate',
  product_satisfaction_count: 'ws.records.sessionReports.overall.metric.productSatisfactionCount',
}

export const OVERALL_METRIC_TOOLTIP_KEY: Record<string, string> = {
  total_session_count: 'ws.records.sessionReports.overall.tooltip.totalSessionCount',
  pure_bot_session_count: 'ws.records.sessionReports.overall.tooltip.pureBotSessionCount',
  pure_human_session_count: 'ws.records.sessionReports.overall.tooltip.pureHumanSessionCount',
  bot_human_session_count: 'ws.records.sessionReports.overall.tooltip.botHumanSessionCount',
  human_involved_session_count: 'ws.records.sessionReports.overall.tooltip.humanInvolvedSessionCount',
  effective_session_count: 'ws.records.sessionReports.overall.tooltip.effectiveSessionCount',
  visitor_message_count: 'ws.records.sessionReports.overall.tooltip.visitorMessageCount',
  agent_message_count: 'ws.records.sessionReports.overall.tooltip.agentMessageCount',
  unreplied_session_count: 'ws.records.sessionReports.overall.tooltip.unrepliedSessionCount',
  visitor_silent_session_count: 'ws.records.sessionReports.overall.tooltip.visitorSilentSessionCount',
  queued_session_count: 'ws.records.sessionReports.overall.tooltip.queuedSessionCount',
  assigned_queue_session_count: 'ws.records.sessionReports.overall.tooltip.assignedQueueSessionCount',
  unassigned_queue_session_count: 'ws.records.sessionReports.overall.tooltip.unassignedQueueSessionCount',
  avg_queue_duration_seconds: 'ws.records.sessionReports.overall.tooltip.avgQueueDurationSeconds',
  max_queue_duration_seconds: 'ws.records.sessionReports.overall.tooltip.maxQueueDurationSeconds',
  queue_assign_rate: 'ws.records.sessionReports.overall.tooltip.queueAssignRate',
  avg_first_human_response_seconds: 'ws.records.sessionReports.overall.tooltip.avgFirstHumanResponseSeconds',
  avg_agent_response_seconds: 'ws.records.sessionReports.overall.tooltip.avgAgentResponseSeconds',
  avg_human_session_duration_seconds: 'ws.records.sessionReports.overall.tooltip.avgHumanSessionDurationSeconds',
  satisfaction_invitation_count: 'ws.records.sessionReports.overall.tooltip.satisfactionInvitationCount',
  satisfaction_submission_count: 'ws.records.sessionReports.overall.tooltip.satisfactionSubmissionCount',
  satisfaction_participation_rate: 'ws.records.sessionReports.overall.tooltip.satisfactionParticipationRate',
  satisfaction_submission_rate: 'ws.records.sessionReports.overall.tooltip.satisfactionSubmissionRate',
  product_satisfaction_count: 'ws.records.sessionReports.overall.tooltip.productSatisfactionCount',
}

export const OVERALL_DISTRIBUTION_LABEL_KEY: Record<string, string> = {
  satisfaction_resolution: 'ws.records.sessionReports.overall.distribution.satisfactionResolution',
  service_satisfaction_rating: 'ws.records.sessionReports.overall.distribution.serviceSatisfactionRating',
  product_satisfaction_rating: 'ws.records.sessionReports.overall.distribution.productSatisfactionRating',
}

const RESOLUTION_SLICE_LABEL_KEY: Record<string, string> = {
  resolved: 'ws.records.sessionReports.overall.distribution.slice.resolved',
  unresolved: 'ws.records.sessionReports.overall.distribution.slice.unresolved',
}

const DISTRIBUTION_METRIC_SEPARATOR = ':'

export function groupLabelKey(group: string): string {
  return OVERALL_GROUP_LABEL_KEY[group] ?? group
}

export function metricLabelKey(key: string): string {
  return OVERALL_METRIC_LABEL_KEY[key] ?? key
}

export function metricTooltipKey(key: string): string | undefined {
  return OVERALL_METRIC_TOOLTIP_KEY[key]
}

export function distributionLabelKey(key: string): string {
  return OVERALL_DISTRIBUTION_LABEL_KEY[key] ?? key
}

export function distributionSliceDisplayLabel(
  distributionKey: string,
  slice: MetricDistributionSlice,
  locale: Locale,
): string {
  if (distributionKey === 'satisfaction_resolution') {
    const key = RESOLUTION_SLICE_LABEL_KEY[slice.key]
    if (key) return t(key, locale)
  }
  return slice.label
}

export function metricDisplayLabel(
  key: string,
  locale: Locale,
  distributions: MetricDistribution[] = [],
): string {
  const parsed = parseDistributionMetricKey(key)
  if (!parsed) return t(metricLabelKey(key), locale)

  const distribution = distributions.find((item) => item.key === parsed.distributionKey)
  const slice = distribution?.slices.find((item) => item.key === parsed.sliceKey)
  if (!distribution || !slice) return key

  return `${t(distributionLabelKey(distribution.key), locale)}: ${distributionSliceDisplayLabel(
    distribution.key,
    slice,
    locale,
  )}`
}

function parseDistributionMetricKey(
  key: string,
): { distributionKey: string; sliceKey: string } | null {
  const separatorIndex = key.indexOf(DISTRIBUTION_METRIC_SEPARATOR)
  if (separatorIndex <= 0 || separatorIndex === key.length - 1) return null
  return {
    distributionKey: key.slice(0, separatorIndex),
    sliceKey: key.slice(separatorIndex + 1),
  }
}

export function isDurationFormat(format: MetricFormat): boolean {
  return format === 'duration_seconds'
}

/** Render a metric value by its format. Counts → localized number, durations →
 *  mm:ss / HH:mm:ss, percent → x.x%, null → "—" (or 0 for counts). */
export function formatMetricValue(value: number | null, format: MetricFormat): string {
  if (value === null || value === undefined) {
    return format === 'integer' ? '0' : '—'
  }
  if (format === 'duration_seconds') return formatDuration(value)
  if (format === 'percent') return `${(value * 100).toFixed(1)}%`
  return value.toLocaleString()
}

/** Numeric value for charting (null → 0). */
export function metricChartValue(value: number | null): number {
  return value ?? 0
}
