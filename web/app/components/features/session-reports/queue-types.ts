import type { Locale } from '@/context/locale-store'
import type {
  QueueMetricFormat,
  QueueMetricGroup,
  QueueMetricKey,
  QueueStatus,
  QueueType,
} from '@/models/session-report'
import type { MetricDistribution } from '@/models/session-report-overall'
import { formatDuration } from '@/utils/format-duration'
import { t } from '@/utils/i18n'
import { metricDisplayLabel } from './overall/metric-format'

export const QUEUE_METRIC_GROUPS: QueueMetricGroup[] = [
  'queue_access',
  'human_messages',
  'service_efficiency',
  'satisfaction',
]

export const queueGroupLabelKey: Record<QueueMetricGroup, string> = {
  queue_access: 'ws.records.sessionReports.overall.group.queueAccess',
  human_messages: 'ws.records.sessionReports.overall.group.humanMessages',
  service_efficiency: 'ws.records.sessionReports.overall.group.serviceEfficiency',
  satisfaction: 'ws.records.sessionReports.overall.group.satisfaction',
}

export const queueTypeLabelKey: Record<QueueType, string> = {
  employee_group: 'ws.records.sessionReports.queues.type.group',
}

export const queueStatusLabelKey: Record<QueueStatus, string> = {
  active: 'ws.records.sessionReports.queues.status.active',
  inactive: 'ws.records.sessionReports.queues.status.inactive',
  deleted: 'ws.records.sessionReports.queues.status.deleted',
}

export const queueMetricLabelKey: Record<QueueMetricKey, string> = {
  queued_session_count: 'ws.records.sessionReports.overall.metric.queuedSessionCount',
  assigned_queue_session_count: 'ws.records.sessionReports.overall.metric.assignedQueueSessionCount',
  unassigned_queue_session_count: 'ws.records.sessionReports.overall.metric.unassignedQueueSessionCount',
  queue_assign_rate: 'ws.records.sessionReports.overall.metric.queueAssignRate',
  avg_queue_duration_seconds: 'ws.records.sessionReports.overall.metric.avgQueueDurationSeconds',
  max_queue_duration_seconds: 'ws.records.sessionReports.overall.metric.maxQueueDurationSeconds',
  final_session_count: 'ws.records.sessionReports.queues.metric.finalSessionCount',
  effective_session_count: 'ws.records.sessionReports.overall.metric.effectiveSessionCount',
  user_message_count: 'ws.records.sessionReports.overall.metric.visitorMessageCount',
  agent_message_count: 'ws.records.sessionReports.overall.metric.agentMessageCount',
  unreplied_session_count: 'ws.records.sessionReports.overall.metric.unrepliedSessionCount',
  visitor_silent_session_count: 'ws.records.sessionReports.overall.metric.visitorSilentSessionCount',
  avg_first_human_response_seconds: 'ws.records.sessionReports.overall.metric.avgFirstHumanResponseSeconds',
  avg_agent_response_seconds: 'ws.records.sessionReports.overall.metric.avgAgentResponseSeconds',
  avg_human_session_duration_seconds: 'ws.records.sessionReports.overall.metric.avgHumanSessionDurationSeconds',
  satisfaction_invitation_count: 'ws.records.sessionReports.overall.metric.satisfactionInvitationCount',
  satisfaction_submission_count: 'ws.records.sessionReports.overall.metric.satisfactionSubmissionCount',
  satisfaction_participation_rate: 'ws.records.sessionReports.overall.metric.satisfactionParticipationRate',
  satisfaction_submission_rate: 'ws.records.sessionReports.overall.metric.satisfactionSubmissionRate',
  product_satisfaction_count: 'ws.records.sessionReports.overall.metric.productSatisfactionCount',
}

export const queueMetricFormat: Record<QueueMetricKey, QueueMetricFormat> = {
  queued_session_count: 'integer',
  assigned_queue_session_count: 'integer',
  unassigned_queue_session_count: 'integer',
  queue_assign_rate: 'percent',
  avg_queue_duration_seconds: 'duration_seconds',
  max_queue_duration_seconds: 'duration_seconds',
  final_session_count: 'integer',
  effective_session_count: 'integer',
  user_message_count: 'integer',
  agent_message_count: 'integer',
  unreplied_session_count: 'integer',
  visitor_silent_session_count: 'integer',
  avg_first_human_response_seconds: 'duration_seconds',
  avg_agent_response_seconds: 'duration_seconds',
  avg_human_session_duration_seconds: 'duration_seconds',
  satisfaction_invitation_count: 'integer',
  satisfaction_submission_count: 'integer',
  satisfaction_participation_rate: 'percent',
  satisfaction_submission_rate: 'percent',
  product_satisfaction_count: 'integer',
}

export const queueOverviewGroups: Record<QueueMetricGroup, QueueMetricKey[]> = {
  queue_access: [
    'queued_session_count',
    'assigned_queue_session_count',
    'unassigned_queue_session_count',
    'queue_assign_rate',
    'avg_queue_duration_seconds',
    'max_queue_duration_seconds',
  ],
  human_messages: [
    'final_session_count',
    'effective_session_count',
    'user_message_count',
    'agent_message_count',
    'unreplied_session_count',
    'visitor_silent_session_count',
  ],
  service_efficiency: [
    'avg_first_human_response_seconds',
    'avg_agent_response_seconds',
    'avg_human_session_duration_seconds',
  ],
  satisfaction: [
    'satisfaction_invitation_count',
    'satisfaction_submission_count',
    'satisfaction_participation_rate',
    'satisfaction_submission_rate',
    'product_satisfaction_count',
  ],
}

export function formatQueueMetricValue(
  value: number | null | undefined,
  format: QueueMetricFormat,
): string {
  if (value === null || value === undefined) {
    return format === 'integer' ? '0' : '—'
  }
  if (format === 'duration_seconds') return formatDuration(value)
  if (format === 'percent') return `${(value * 100).toFixed(1)}%`
  return value.toLocaleString()
}

export function queueMetricDisplayLabel(
  key: string,
  locale: Locale,
  distributions: MetricDistribution[] = [],
): string {
  if (isQueueMetricKey(key)) {
    return t(queueMetricLabelKey[key], locale)
  }
  return metricDisplayLabel(key, locale, distributions)
}

function isQueueMetricKey(key: string): key is QueueMetricKey {
  return Object.prototype.hasOwnProperty.call(queueMetricLabelKey, key)
}
