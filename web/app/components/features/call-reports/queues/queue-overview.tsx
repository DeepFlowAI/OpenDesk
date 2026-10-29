'use client'

import type { CallMetricDistribution, CallOverallMetric } from '@/models/call-report-overall'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { CallMetricGroupBlock } from '../overall/metric-group-block'

export const QUEUE_GROUP_ORDER = [
  'queue_flow',
  'queue_outcomes',
  'queue_waiting',
  'agent_response',
]

type Props = {
  metrics: CallOverallMetric[]
  distributions: CallMetricDistribution[]
  loading?: boolean
}

export function CallQueueOverview({ metrics, distributions, loading }: Props) {
  const { locale } = useLocaleStore()
  const groups = QUEUE_GROUP_ORDER.filter(
    (group) => loading || metrics.some((metric) => metric.group === group && metric.available),
  )

  return (
    <div className="space-y-6">
      <h2 className="text-sm font-semibold text-foreground">
        {t('ws.records.callReports.queues.overviewTitle', locale)}
      </h2>
      {groups.map((group) => {
        const groupMetrics = metrics.filter((metric) => metric.group === group && metric.available)
        return (
          <CallMetricGroupBlock
            key={group}
            groupKey={group}
            metrics={groupMetrics.length > 0 ? groupMetrics : skeletonMetrics(group)}
            distributions={distributions.filter((item) => item.group === group)}
            loading={loading}
          />
        )
      })}
    </div>
  )
}

function skeletonMetrics(group: string): CallOverallMetric[] {
  return Array.from({ length: 4 }, (_, index) => ({
    key: `skeleton-${group}-${index}`,
    value: null,
    format: 'integer',
    level: 'primary',
    group,
    available: true,
  }))
}
