'use client'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { QueueMetricGroup, QueueReportMetrics } from '@/models/session-report'
import type { MetricDistribution } from '@/models/session-report-overall'
import { SatisfactionDistributionCharts } from './overall/satisfaction-distribution-charts'
import {
  formatQueueMetricValue,
  QUEUE_METRIC_GROUPS,
  queueGroupLabelKey,
  queueMetricFormat,
  queueMetricLabelKey,
  queueOverviewGroups,
} from './queue-types'

type Props = {
  metrics?: QueueReportMetrics
  distributions?: MetricDistribution[]
  loading?: boolean
}

export function QueueOverviewCards({ metrics, distributions = [], loading }: Props) {
  return (
    <div className="space-y-3">
      {QUEUE_METRIC_GROUPS.map((group) => (
        <MetricGroup
          key={group}
          group={group}
          metrics={metrics}
          distributions={distributions.filter((item) => item.group === group)}
          loading={loading}
        />
      ))}
    </div>
  )
}

function MetricGroup({
  group,
  metrics,
  distributions,
  loading,
}: {
  group: QueueMetricGroup
  metrics?: QueueReportMetrics
  distributions: MetricDistribution[]
  loading?: boolean
}) {
  const { locale } = useLocaleStore()
  return (
    <div>
      <h3 className="mb-1.5 text-xs font-medium text-muted-foreground">
        {t(queueGroupLabelKey[group], locale)}
      </h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
        {queueOverviewGroups[group].map((key) => (
          <Card
            key={key}
            label={t(queueMetricLabelKey[key], locale)}
            value={formatQueueMetricValue(metrics?.[key], queueMetricFormat[key])}
            loading={loading}
          />
        ))}
      </div>
      {group === 'satisfaction' ? (
        <SatisfactionDistributionCharts distributions={distributions} loading={loading} />
      ) : null}
    </div>
  )
}

function Card({
  label,
  value,
  loading,
}: {
  label: string
  value: string
  loading?: boolean
}) {
  return (
    <div className="flex min-h-[52px] flex-col justify-center gap-0.5 rounded-lg border border-border bg-background px-3 py-2">
      <span className="truncate text-xs leading-tight text-muted-foreground" title={label}>
        {label}
      </span>
      {loading ? (
        <span className="h-5 w-12 animate-pulse rounded bg-muted" aria-busy="true" />
      ) : (
        <span className="truncate text-lg font-semibold leading-tight tracking-tight text-foreground">
          {value}
        </span>
      )}
    </div>
  )
}
