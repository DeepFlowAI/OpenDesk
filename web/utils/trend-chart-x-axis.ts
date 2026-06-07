import type { TrendType } from '@/models/session-report'

/** Whether to show an x-axis label under bucket `index` (aligned with bar columns). */
export function shouldShowTrendXLabel(
  index: number,
  total: number,
  trend: TrendType,
): boolean {
  if (total === 0) return false
  if (index === total - 1) return true

  switch (trend) {
    case 'half_hour':
      return true
    case 'hour':
      return true
    case 'day':
      if (total <= 14) return true
      return index % Math.max(1, Math.ceil(total / 10)) === 0
    case 'week':
    case 'month':
      if (total <= 12) return true
      return index % Math.max(1, Math.ceil(total / 8)) === 0
    default:
      return index % Math.max(1, Math.ceil(total / 7)) === 0
  }
}

/** Compact x-axis text for intraday half-hour buckets. */
export function formatTrendXLabel(label: string, index: number, trend: TrendType): string {
  if (trend !== 'half_hour') return label
  return index % 2 === 0 ? label : label.slice(3)
}
