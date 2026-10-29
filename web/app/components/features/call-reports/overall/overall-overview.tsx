'use client'

import { useLocaleStore } from '@/context/locale-store'
import type {
  CallMetricDistribution,
  CallOverallMetric,
} from '@/models/call-report-overall'
import { t } from '@/utils/i18n'
import { CALL_GROUP_ORDER, orderedCallGroups } from './group-utils'
import { CallMetricGroupBlock } from './metric-group-block'

type Props = {
  metrics: CallOverallMetric[]
  distributions: CallMetricDistribution[]
  loading?: boolean
}

export function CallOverallOverview({ metrics, distributions, loading }: Props) {
  const { locale } = useLocaleStore()
  const groups = metrics.length > 0 ? orderedCallGroups(metrics) : [...CALL_GROUP_ORDER]
  return (
    <div className="space-y-6">
      <h2 className="text-sm font-semibold text-foreground">
        {t('ws.records.callReports.overall.overviewTitle', locale)}
      </h2>
      {groups.map((group) => {
        const groupMetrics = metrics.filter((metric) => metric.group === group && metric.available)
        if (!loading && groupMetrics.length === 0) return null
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
