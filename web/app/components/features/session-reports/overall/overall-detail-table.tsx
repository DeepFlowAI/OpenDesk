'use client'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type {
  MetricDistribution,
  OverallTrendBucket,
  OverallTrendDescriptor,
} from '@/models/session-report-overall'
import { formatMetricValue, metricDisplayLabel } from './metric-format'

type Props = {
  buckets: OverallTrendBucket[]
  descriptors: OverallTrendDescriptor[]
  distributions?: MetricDistribution[]
}

/** Detail table: all metrics of the selected group per time bucket. */
export function OverallDetailTable({ buckets, descriptors, distributions = [] }: Props) {
  const { locale } = useLocaleStore()
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <div className="min-w-max">
        <div className="flex h-12 items-center gap-4 bg-[#F8F8F8] px-6 text-xs font-semibold text-muted-foreground">
          <div className="w-[140px] shrink-0">
            {t('ws.records.sessionReports.trend.colTime', locale)}
          </div>
          {descriptors.map((d) => (
            <div key={d.key} className="w-[140px] shrink-0 text-center">
              {metricDisplayLabel(d.key, locale, distributions)}
            </div>
          ))}
        </div>
        <div className="max-h-[480px] overflow-auto">
          {buckets.map((bucket) => {
            const valueByKey = new Map(bucket.metrics.map((m) => [m.key, m]))
            return (
              <div
                key={bucket.label}
                className="flex h-[52px] items-center gap-4 border-b border-[#F0F0F0] px-6 text-[13px] text-foreground last:border-b-0"
              >
                <div className="w-[140px] shrink-0">{bucket.label}</div>
                {descriptors.map((d) => {
                  const metric = valueByKey.get(d.key)
                  return (
                    <div key={d.key} className="w-[140px] shrink-0 text-center">
                      {formatMetricValue(metric?.value ?? null, d.format)}
                    </div>
                  )
                })}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
