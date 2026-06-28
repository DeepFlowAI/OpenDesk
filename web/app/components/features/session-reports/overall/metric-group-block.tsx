'use client'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { MetricDistribution, MetricResult } from '@/models/session-report-overall'
import { formatMetricValue, groupLabelKey, metricLabelKey, metricTooltipKey } from './metric-format'
import { SatisfactionDistributionCharts } from './satisfaction-distribution-charts'

type Props = {
  groupKey: string
  /** Metrics of this group, in registry order. */
  metrics: MetricResult[]
  distributions?: MetricDistribution[]
  loading?: boolean
}

/** One metric-group overview block: group title + its metric cards. */
export function MetricGroupBlock({ groupKey, metrics, distributions = [], loading }: Props) {
  const { locale } = useLocaleStore()
  if (metrics.length === 0) return null

  return (
    <div>
      <h3 className="mb-1.5 text-xs font-medium text-muted-foreground">
        {t(groupLabelKey(groupKey), locale)}
      </h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {metrics.map((metric) => (
          <MetricCard key={metric.key} metric={metric} loading={loading} />
        ))}
      </div>
      {groupKey === 'satisfaction' ? (
        <SatisfactionDistributionCharts distributions={distributions} loading={loading} />
      ) : null}
    </div>
  )
}

function MetricCard({ metric, loading }: { metric: MetricResult; loading?: boolean }) {
  const { locale } = useLocaleStore()
  const tooltipKey = metricTooltipKey(metric.key)
  const tooltip = tooltipKey ? t(tooltipKey, locale) : undefined
  return (
    <div className="flex min-h-[52px] flex-col justify-center gap-0.5 rounded-lg border border-border bg-background px-3 py-2">
      <span className="truncate text-xs leading-tight text-muted-foreground" title={tooltip}>
        {t(metricLabelKey(metric.key), locale)}
      </span>
      {loading ? (
        <span className="h-5 w-12 animate-pulse rounded bg-muted" aria-busy="true" />
      ) : (
        <span className="truncate text-lg font-semibold leading-tight tracking-tight text-foreground">
          {formatMetricValue(metric.value, metric.format)}
        </span>
      )}
    </div>
  )
}
