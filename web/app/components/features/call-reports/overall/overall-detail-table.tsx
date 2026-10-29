'use client'

import { useLocaleStore } from '@/context/locale-store'
import type {
  CallOverallMetric,
  CallOverallTrendBucket,
} from '@/models/call-report-overall'
import { t } from '@/utils/i18n'
import { callMetricLabel, formatCallMetric } from './metric-format'

type Props = {
  buckets: CallOverallTrendBucket[]
  descriptors: CallOverallMetric[]
}

export function CallOverallDetailTable({ buckets, descriptors }: Props) {
  const { locale } = useLocaleStore()
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <div className="max-h-[480px] min-w-max overflow-auto">
        <table className="w-full border-collapse text-[13px] text-foreground">
          <thead className="sticky top-0 z-10 bg-muted text-xs font-semibold text-foreground/80">
            <tr className="h-12">
              <th scope="col" className="w-[180px] px-6 text-left">
                {t('ws.records.callReports.overall.trend.colTime', locale)}
              </th>
              {descriptors.map((descriptor) => (
                <th key={descriptor.key} scope="col" className="w-[166px] px-4 text-right">
                  {callMetricLabel(descriptor.key, locale)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
          {buckets.map((bucket) => {
            const values = new Map(bucket.metrics.map((metric) => [metric.key, metric]))
            return (
              <tr
                key={`${bucket.bucket_start}-${bucket.label}`}
                className="h-[52px] border-b border-border last:border-b-0"
              >
                <th scope="row" className="px-6 text-left font-normal">{bucket.label}</th>
                {descriptors.map((descriptor) => (
                  <td key={descriptor.key} className="px-4 text-right font-mono">
                    {formatCallMetric(
                      values.get(descriptor.key)?.value ?? null,
                      descriptor.format,
                      locale,
                    )}
                  </td>
                ))}
              </tr>
            )
          })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
