'use client'

import { useLocaleStore } from '@/context/locale-store'
import { useSessionReportsOverview } from '@/service/use-session-reports'
import { formatDuration } from '@/utils/format-duration'
import { t } from '@/utils/i18n'
import type { MetricKey } from '@/models/session-report'
import { metricLabelKey, METRIC_KEYS, isDurationMetric } from './types'

type Props = {
  start: string
  end: string
  employeeId?: number
}

export function OverviewCards({ start, end, employeeId }: Props) {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useSessionReportsOverview({
    start,
    end,
    employee_id: employeeId,
  })

  return (
    <div>
      <h2 className="mb-3 text-base font-semibold text-foreground">
        {t('ws.records.sessionReports.overview.title', locale)}
      </h2>
      <div className="flex gap-4">
        {METRIC_KEYS.map((key) => (
          <Card
            key={key}
            labelKey={metricLabelKey[key]}
            value={renderValue(key, data)}
            loading={isLoading}
          />
        ))}
      </div>
    </div>
  )
}

function renderValue(metric: MetricKey, data: any): string {
  if (!data) return '0'
  if (isDurationMetric(metric)) {
    return formatDuration(data.avg_duration_seconds)
  }
  const v = data[metric]
  return typeof v === 'number' ? v.toLocaleString() : '0'
}

function Card({
  labelKey,
  value,
  loading,
}: {
  labelKey: string
  value: string
  loading?: boolean
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="flex h-24 flex-1 flex-col justify-center gap-2 rounded-[10px] border border-border bg-background px-5 py-4">
      <span className="text-sm text-muted-foreground">{t(labelKey, locale)}</span>
      {loading ? (
        <span className="h-8 w-16 animate-pulse rounded bg-muted" aria-busy="true" />
      ) : (
        <span className="text-[32px] font-semibold leading-none tracking-tight text-foreground">
          {value}
        </span>
      )}
    </div>
  )
}
