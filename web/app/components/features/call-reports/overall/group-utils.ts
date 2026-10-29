import type { CallOverallMetric } from '@/models/call-report-overall'

export const CALL_GROUP_ORDER = [
  'call_overview',
  'inbound_service',
  'outbound_service',
  'service_efficiency',
  'satisfaction',
] as const

export function orderedCallGroups(metrics: CallOverallMetric[]): string[] {
  return Array.from(
    new Set(metrics.filter((metric) => metric.available).map((metric) => metric.group)),
  )
}
