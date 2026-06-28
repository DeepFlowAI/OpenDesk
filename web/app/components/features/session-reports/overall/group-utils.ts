import type { MetricResult } from '@/models/session-report-overall'

/** Unique group keys in first-appearance order (the backend registry order). */
export function orderedGroups(metrics: MetricResult[]): string[] {
  const seen = new Set<string>()
  const groups: string[] = []
  for (const metric of metrics) {
    if (!seen.has(metric.group)) {
      seen.add(metric.group)
      groups.push(metric.group)
    }
  }
  return groups
}
