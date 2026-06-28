'use client'

import { useMemo } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { MetricDistribution, MetricResult } from '@/models/session-report-overall'
import { MetricGroupBlock } from './metric-group-block'
import { orderedGroups } from './group-utils'

type Props = {
  metrics: MetricResult[]
  distributions?: MetricDistribution[]
  loading?: boolean
}

/** Metric-group overview: renders one block per group (all available metrics). */
export function OverallOverview({ metrics, distributions = [], loading }: Props) {
  const { locale } = useLocaleStore()
  const groups = useMemo(() => orderedGroups(metrics), [metrics])

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-semibold text-foreground">
        {t('ws.records.sessionReports.overview.title', locale)}
      </h2>
      {groups.map((group) => (
        <MetricGroupBlock
          key={group}
          groupKey={group}
          metrics={metrics.filter((m) => m.group === group && m.available)}
          distributions={distributions.filter((item) => item.group === group)}
          loading={loading}
        />
      ))}
    </div>
  )
}
