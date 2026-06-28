'use client'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { QueueMetricGroup, QueueReportMetrics } from '@/models/session-report'
import {
  formatQueueMetricValue,
  queueGroupLabelKey,
  queueMetricFormat,
  queueMetricLabelKey,
  queueOverviewGroups,
} from './queue-types'

type Props = {
  metrics?: QueueReportMetrics
  loading?: boolean
}

export function QueueOverviewCards({ metrics, loading }: Props) {
  return (
    <div className="space-y-5">
      {(['queue_access', 'human_messages', 'service_efficiency'] as QueueMetricGroup[]).map((group) => (
        <MetricGroup key={group} group={group} metrics={metrics} loading={loading} />
      ))}
    </div>
  )
}

function MetricGroup({
  group,
  metrics,
  loading,
}: {
  group: QueueMetricGroup
  metrics?: QueueReportMetrics
  loading?: boolean
}) {
  const { locale } = useLocaleStore()
  return (
    <div>
      <h3 className="mb-3 text-sm font-semibold text-muted-foreground">
        {t(queueGroupLabelKey[group], locale)}
      </h3>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6">
        {queueOverviewGroups[group].map((key) => (
          <Card
            key={key}
            label={t(queueMetricLabelKey[key], locale)}
            value={formatQueueMetricValue(metrics?.[key], queueMetricFormat[key])}
            loading={loading}
          />
        ))}
      </div>
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
    <div className="flex h-24 flex-1 flex-col justify-center gap-2 rounded-[10px] border border-border bg-background px-5 py-4">
      <span className="text-sm text-muted-foreground">{label}</span>
      {loading ? (
        <span className="h-8 w-16 animate-pulse rounded bg-muted" aria-busy="true" />
      ) : (
        <span className="text-[28px] font-semibold leading-none tracking-tight text-foreground">
          {value}
        </span>
      )}
    </div>
  )
}
