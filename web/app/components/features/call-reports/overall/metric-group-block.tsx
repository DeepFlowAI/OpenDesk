'use client'

import { IconInfoCircle } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import type {
  CallMetricDistribution,
  CallOverallMetric,
} from '@/models/call-report-overall'
import { CallDistributionCharts } from './distribution-charts'
import {
  callGroupLabel,
  callMetricLabel,
  callMetricTooltip,
  formatCallMetric,
} from './metric-format'

type Props = {
  groupKey: string
  metrics: CallOverallMetric[]
  distributions: CallMetricDistribution[]
  loading?: boolean
}

export function CallMetricGroupBlock({ groupKey, metrics, distributions, loading }: Props) {
  const { locale } = useLocaleStore()
  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold text-foreground">
        {callGroupLabel(groupKey, locale)}
      </h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {metrics.map((metric) => loading ? (
          <MetricSkeleton key={metric.key} />
        ) : (
          <MetricCard key={metric.key} metric={metric} />
        ))}
      </div>
      <CallDistributionCharts distributions={distributions} loading={loading} />
    </section>
  )
}

function MetricCard({ metric }: { metric: CallOverallMetric }) {
  const { locale } = useLocaleStore()
  const descriptionId = `call-metric-${metric.key}`
  return (
    <div className="relative flex min-h-[76px] flex-col justify-center gap-1 rounded-lg border border-border bg-card px-3 py-2">
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="truncate text-xs text-muted-foreground">
          {callMetricLabel(metric.key, locale)}
        </span>
        <span className="group relative shrink-0">
          <button
            type="button"
            className="flex rounded-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
            aria-describedby={descriptionId}
            aria-label={callMetricTooltip(metric.key, locale)}
          >
            <IconInfoCircle size={14} />
          </button>
          <span
            id={descriptionId}
            role="tooltip"
            className="pointer-events-none absolute left-1/2 top-5 z-20 hidden w-64 -translate-x-1/2 rounded-md border border-border bg-popover p-2 text-xs leading-5 text-popover-foreground shadow-md group-hover:block group-focus-within:block"
          >
            {callMetricTooltip(metric.key, locale)}
          </span>
        </span>
      </div>
      <span className="truncate font-mono text-xl font-semibold text-foreground">
        {formatCallMetric(metric.value, metric.format, locale)}
      </span>
    </div>
  )
}

function MetricSkeleton() {
  return (
    <div className="flex min-h-[76px] animate-pulse flex-col justify-center gap-2 rounded-lg border border-border bg-card px-3 py-2" aria-busy="true">
      <span className="h-3 w-20 rounded bg-muted" />
      <span className="h-6 w-16 rounded bg-muted" />
    </div>
  )
}
