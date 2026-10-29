import type { Locale } from '@/context/locale-store'
import type {
  CallDistributionSlice,
  CallMetricFormat,
} from '@/models/call-report-overall'
import { formatDuration } from '@/utils/format-duration'
import { t } from '@/utils/i18n'

const PREFIX = 'ws.records.callReports.overall'
const QUEUE_PREFIX = 'ws.records.callReports.queues'
const EMPLOYEE_PREFIX = 'ws.records.callReports.employees'

const GROUP_KEYS: Record<string, string> = {
  call_overview: `${PREFIX}.group.callOverview`,
  inbound_service: `${PREFIX}.group.inboundService`,
  outbound_service: `${PREFIX}.group.outboundService`,
  service_efficiency: `${PREFIX}.group.serviceEfficiency`,
  satisfaction: `${PREFIX}.group.satisfaction`,
  queue_flow: `${QUEUE_PREFIX}.group.queueFlow`,
  queue_outcomes: `${QUEUE_PREFIX}.group.queueOutcomes`,
  queue_waiting: `${QUEUE_PREFIX}.group.queueWaiting`,
  agent_response: `${QUEUE_PREFIX}.group.agentResponse`,
  workload: `${EMPLOYEE_PREFIX}.group.workload`,
  offer_response: `${EMPLOYEE_PREFIX}.group.offerResponse`,
  efficiency: `${EMPLOYEE_PREFIX}.group.efficiency`,
  collaboration: `${EMPLOYEE_PREFIX}.group.collaboration`,
}

const METRIC_NAMES = [
  'call_count',
  'inbound_call_count',
  'outbound_call_count',
  'active_call_count',
  'ended_call_count',
  'inbound_human_request_count',
  'inbound_human_wait_count',
  'inbound_agent_ringing_count',
  'inbound_agent_answered_count',
  'inbound_human_answer_rate',
  'inbound_queue_answer_rate',
  'inbound_short_abandon_count',
  'inbound_short_abandon_rate',
  'inbound_avg_wait_seconds',
  'inbound_service_level_20s',
  'outbound_attempt_count',
  'outbound_customer_connected_count',
  'outbound_agent_connected_count',
  'outbound_customer_connect_rate',
  'outbound_avg_customer_ring_seconds',
  'outbound_avg_talk_seconds',
  'human_served_call_count',
  'total_human_talk_seconds',
  'avg_human_talk_seconds',
  'avg_total_duration_seconds',
  'customer_hangup_rate',
  'survey_triggered_count',
  'survey_answered_count',
  'survey_participation_rate',
  'survey_completed_count',
  'survey_completion_rate',
] as const

const METRIC_KEYS = Object.fromEntries(
  METRIC_NAMES.map((key) => [key, `${PREFIX}.metric.${key}`]),
) as Record<string, string>

const QUEUE_METRIC_NAMES = [
  'queue_call_count',
  'queue_entry_count',
  'first_queue_entry_count',
  'transfer_in_entry_count',
  'queue_answered_count',
  'queue_answer_rate',
  'queue_abandoned_count',
  'queue_abandon_rate',
  'queue_short_abandon_count',
  'queue_short_abandon_rate',
  'queue_timeout_count',
  'queue_transfer_out_count',
  'avg_answer_wait_seconds',
  'avg_abandon_wait_seconds',
  'avg_queue_wait_seconds',
  'max_queue_wait_seconds',
  'queue_service_level_20s',
  'offered_call_count',
  'offer_attempt_count',
  'offer_accepted_count',
  'offer_rejected_count',
  'offer_timeout_count',
  'offer_accept_rate',
] as const

for (const key of QUEUE_METRIC_NAMES) METRIC_KEYS[key] = `${QUEUE_PREFIX}.metric.${key}`

const EMPLOYEE_METRIC_NAMES = [
  'participated_call_count', 'handled_call_count', 'reception_segment_count',
  'inbound_handled_call_count', 'outbound_attempt_count', 'outbound_customer_answered_count',
  'outbound_handled_call_count', 'transfer_in_segment_count', 'offered_call_count',
  'offer_attempt_count', 'offer_accepted_count', 'offer_accept_rate', 'offer_rejected_count',
  'offer_timeout_count', 'offer_timeout_rate', 'avg_offer_response_seconds', 'total_talk_seconds',
  'avg_talk_seconds', 'held_segment_count', 'total_hold_seconds', 'avg_hold_seconds',
  'total_after_call_work_seconds', 'avg_after_call_work_seconds', 'avg_handle_seconds',
  'transfer_attempt_count', 'transfer_completed_count', 'transfer_success_rate',
  'transfer_failed_count', 'consult_attempt_count', 'consult_connected_count',
  'consult_success_rate', 'conference_join_count',
] as const

for (const key of EMPLOYEE_METRIC_NAMES) METRIC_KEYS[key] = `${EMPLOYEE_PREFIX}.metric.${key}`

const TOOLTIP_KEYS = Object.fromEntries(
  METRIC_NAMES.map((key) => [key, `${PREFIX}.tooltip.${key}`]),
) as Record<string, string>

for (const key of QUEUE_METRIC_NAMES) TOOLTIP_KEYS[key] = `${QUEUE_PREFIX}.tooltip.${key}`
for (const key of EMPLOYEE_METRIC_NAMES) TOOLTIP_KEYS[key] = `${EMPLOYEE_PREFIX}.tooltip.${key}`

const DISTRIBUTION_KEYS: Record<string, string> = {
  direction: `${PREFIX}.distribution.direction`,
  call_source: `${PREFIX}.distribution.call_source`,
  actual_reception_type: `${PREFIX}.distribution.actual_reception_type`,
  inbound_call_result: `${PREFIX}.distribution.inbound_call_result`,
  inbound_human_funnel: `${PREFIX}.distribution.inbound_human_funnel`,
  outbound_call_source: `${PREFIX}.distribution.outbound_call_source`,
  outbound_call_result: `${PREFIX}.distribution.outbound_call_result`,
  call_result: `${PREFIX}.distribution.call_result`,
  hangup_party: `${PREFIX}.distribution.hangup_party`,
  hangup_stage: `${PREFIX}.distribution.hangup_stage`,
  satisfaction_result: `${PREFIX}.distribution.satisfaction_result`,
  satisfaction_trigger_source: `${PREFIX}.distribution.satisfaction_trigger_source`,
  satisfaction_primary_option: `${PREFIX}.distribution.satisfaction_primary_option`,
  queue_exit_result: `${QUEUE_PREFIX}.distribution.queueExitResult`,
  queue_wait_duration: `${QUEUE_PREFIX}.distribution.queueWaitDuration`,
  offer_result: `${QUEUE_PREFIX}.distribution.offerResult`,
  reception_entry_reason: `${EMPLOYEE_PREFIX}.distribution.receptionEntryReason`,
  handle_duration: `${EMPLOYEE_PREFIX}.distribution.handleDuration`,
  reception_end_reason: `${EMPLOYEE_PREFIX}.distribution.receptionEndReason`,
}

const LOCALIZED_ENUM_KEYS = new Set([
  'inbound',
  'outbound',
  'agent_dial',
  'manual_outbound_task',
  'auto_outbound',
  'ivr',
  'bot',
  'agent',
  'bot_agent',
  'not_formed',
  'agent_answered',
  'customer_short_abandon',
  'agent_no_answer',
  'customer_no_answer',
  'customer_busy',
  'customer_unreachable',
  'provider_answer_unconfirmed',
  'provider_temporarily_unavailable',
  'invalid_number',
  'ivr_customer_hangup',
  'bot_customer_hangup',
  'bot_completed',
  'canceled',
  'failed',
  'customer',
  'supervisor',
  'system',
  'carrier',
  'unknown',
  'pre_route',
  'customer_ringing',
  'agent_waiting',
  'agent_ringing',
  'in_call',
  'completed',
  'partial',
  'unanswered',
  'not_surveyed',
  'post_call',
  'during_call',
  'auto_transfer',
  'agent_invite',
  'other',
])

export function callGroupLabel(group: string, locale: Locale): string {
  return t(GROUP_KEYS[group] ?? group, locale)
}

export function callMetricLabel(key: string, locale: Locale): string {
  return t(METRIC_KEYS[key] ?? key, locale)
}

export function callMetricTooltip(key: string, locale: Locale): string {
  return t(TOOLTIP_KEYS[key] ?? key, locale)
}

export function callDistributionLabel(key: string, locale: Locale): string {
  return t(DISTRIBUTION_KEYS[key] ?? key, locale)
}

export function callDistributionSliceLabel(
  distributionKey: string,
  slice: CallDistributionSlice,
  locale: Locale,
): string {
  if (distributionKey.startsWith('queue_') || distributionKey === 'offer_result') {
    return t(`${QUEUE_PREFIX}.enum.${slice.key}`, locale)
  }
  if (['reception_entry_reason', 'handle_duration', 'reception_end_reason'].includes(distributionKey)) {
    return t(`${EMPLOYEE_PREFIX}.enum.${slice.key}`, locale)
  }
  if (distributionKey === 'inbound_human_funnel') {
    return callMetricLabel(slice.key, locale)
  }
  if (distributionKey === 'satisfaction_primary_option' && slice.key !== 'other') {
    return slice.label
  }
  if (LOCALIZED_ENUM_KEYS.has(slice.key)) {
    return t(`${PREFIX}.enum.${slice.key}`, locale)
  }
  return slice.label || slice.key
}

export function formatCallMetric(
  value: number | null,
  format: CallMetricFormat,
  locale: Locale,
): string {
  if (value === null || value === undefined) return '—'
  if (format === 'duration_seconds') return formatDuration(value)
  if (format === 'percent') {
    return new Intl.NumberFormat(locale, {
      style: 'percent',
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    }).format(value)
  }
  return new Intl.NumberFormat(locale).format(value)
}

export function callMetricChartValue(value: number | null): number | null {
  return value ?? null
}
