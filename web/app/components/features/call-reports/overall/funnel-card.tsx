'use client'

import { useLocaleStore } from '@/context/locale-store'
import type { CallMetricDistribution } from '@/models/call-report-overall'
import { t } from '@/utils/i18n'
import { callDistributionSliceLabel } from './metric-format'

export function CallFunnelCard({ distribution }: { distribution: CallMetricDistribution }) {
  const { locale } = useLocaleStore()
  const max = Math.max(0, ...distribution.slices.map((slice) => slice.value))

  return (
    <div className="space-y-3 pt-3">
      {distribution.slices.map((slice) => (
        <div key={slice.key} className="space-y-1">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="text-muted-foreground">
              {callDistributionSliceLabel(distribution.key, slice, locale)}
            </span>
            <span className="font-mono text-foreground">{slice.value.toLocaleString(locale)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-sm bg-muted">
            <div
              className="h-full rounded-sm bg-primary"
              style={{ width: `${max > 0 ? (slice.value / max) * 100 : 0}%` }}
            />
          </div>
        </div>
      ))}
      <p className="text-xs leading-5 text-muted-foreground">
        {t('ws.records.callReports.overall.distribution.funnelHint', locale)}
      </p>
    </div>
  )
}
