'use client'

import type { CallMetricDistribution, CallOverallMetric } from '@/models/call-report-overall'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { CallMetricGroupBlock } from '../overall/metric-group-block'

export const EMPLOYEE_GROUP_ORDER = ['workload', 'offer_response', 'efficiency', 'collaboration']

export function CallEmployeeOverview({ metrics, distributions, loading }: {
  metrics: CallOverallMetric[]
  distributions: CallMetricDistribution[]
  loading?: boolean
}) {
  const { locale } = useLocaleStore()
  const groups = EMPLOYEE_GROUP_ORDER.filter(
    (group) => loading || metrics.some((metric) => metric.group === group && metric.available),
  )
  return (
    <div className="space-y-6">
      <h2 className="text-sm font-semibold text-foreground">
        {t('ws.records.callReports.employees.overviewTitle', locale)}
      </h2>
      {groups.map((group) => {
        const groupMetrics = metrics.filter((metric) => metric.group === group && metric.available)
        return <CallMetricGroupBlock key={group} groupKey={group}
          metrics={groupMetrics.length ? groupMetrics : skeletonMetrics(group)}
          distributions={distributions.filter((item) => item.group === group)} loading={loading} />
      })}
    </div>
  )
}

function skeletonMetrics(group: string): CallOverallMetric[] {
  return Array.from({ length: 4 }, (_, index) => ({
    key: `skeleton-${group}-${index}`, value: null, format: 'integer',
    level: 'primary', group, available: true,
  }))
}
