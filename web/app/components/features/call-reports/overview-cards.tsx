'use client'

import { useLocaleStore } from '@/context/locale-store'
import { useCallReportsOverview } from '@/service/use-call-reports'
import { formatDuration } from '@/utils/format-duration'
import { t } from '@/utils/i18n'
import type { CallMetricKey, CallOverviewMetrics } from '@/models/call-report'
import { callMetricLabelKey, CALL_METRIC_KEYS, isDurationMetric } from './types'

type Props = {
  start: string
  end: string
  employeeId?: number
}

export function CallOverviewCards({ start, end, employeeId }: Props) {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useCallReportsOverview({
    start,
    end,
    employee_id: employeeId,
  })

  return (
    <div>
      <h2 className="mb-3 text-base font-semibold text-foreground">
        {t('ws.records.callReports.overview.title', locale)}
      </h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4 2xl:grid-cols-7">
        {CALL_METRIC_KEYS.map((key) => (
          <Card
            key={key}
            labelKey={callMetricLabelKey[key]}
            value={renderValue(key, data ?? null)}
            loading={isLoading}
          />
        ))}
      </div>
    </div>
  )
}

function renderValue(metric: CallMetricKey, data: CallOverviewMetrics | null): string {
  if (!data) return isDurationMetric(metric) ? '—' : '0'
  const value = data[metric]
  if (isDurationMetric(metric)) {
    return typeof value === 'number' ? formatDuration(value) : '—'
  }
  return typeof value === 'number' ? value.toLocaleString() : '0'
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
    <div className="flex h-24 min-w-0 flex-col justify-center gap-2 rounded-[10px] border border-border bg-background px-5 py-4">
      <span className="truncate text-sm text-muted-foreground">{t(labelKey, locale)}</span>
      {loading ? (
        <span className="h-8 w-16 animate-pulse rounded bg-muted" aria-busy="true" />
      ) : (
        <span className="truncate text-[32px] font-semibold leading-none text-foreground">
          {value}
        </span>
      )}
    </div>
  )
}
