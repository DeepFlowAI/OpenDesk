'use client'

import { useLocaleStore } from '@/context/locale-store'
import { useSessionReportsOverview } from '@/service/use-session-reports'
import { formatDuration } from '@/utils/format-duration'
import { t } from '@/utils/i18n'
import type { MetricKey, OverviewMetrics } from '@/models/session-report'
import {
  BASIC_METRIC_KEYS,
  BUSINESS_METRIC_KEYS,
  RECEPTION_METRIC_KEYS,
  isDurationMetric,
  metricLabelKey,
  metricTooltipKey,
  receptionMetricLabelKey,
  receptionMetricTooltipKey,
} from './types'

type Props = {
  start: string
  end: string
  employeeId?: number
  data?: OverviewMetrics
  loading?: boolean
  fetch?: boolean
}

export function OverviewCards({ start, end, employeeId, data: externalData, loading, fetch = true }: Props) {
  const { locale } = useLocaleStore()
  const overviewQuery = useSessionReportsOverview({
    start,
    end,
    employee_id: employeeId,
    enabled: fetch && externalData === undefined,
  })
  const data = externalData ?? overviewQuery.data
  const isLoading = loading ?? overviewQuery.isLoading
  const includeBusinessMetrics = employeeId === undefined
  const businessMetricKeys = BUSINESS_METRIC_KEYS.filter((key) => (
    key !== 'offline_message_count' || (data?.can_view_offline_messages ?? true)
  ))

  return (
    <div className="space-y-5">
      <h2 className="mb-3 text-base font-semibold text-foreground">
        {t('ws.records.sessionReports.overview.title', locale)}
      </h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {BASIC_METRIC_KEYS.map((key) => (
          <Card
            key={key}
            labelKey={metricLabelKey[key]}
            tooltipKey={metricTooltipKey[key]}
            value={renderValue(key, data)}
            loading={isLoading}
          />
        ))}
      </div>
      {includeBusinessMetrics ? (
        <div>
          <h3 className="mb-3 text-sm font-semibold text-muted-foreground">
            {t('ws.records.sessionReports.overview.businessTitle', locale)}
          </h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {businessMetricKeys.map((key) => (
              <Card
                key={key}
                labelKey={metricLabelKey[key]}
                tooltipKey={metricTooltipKey[key]}
                value={renderValue(key, data)}
                loading={isLoading}
              />
            ))}
          </div>
        </div>
      ) : null}
      <div>
        <h3 className="mb-3 text-sm font-semibold text-muted-foreground">
          {t('ws.records.sessionReports.overview.receptionTitle', locale)}
        </h3>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {RECEPTION_METRIC_KEYS.map((key) => (
            <Card
              key={key}
              labelKey={receptionMetricLabelKey[key]}
              tooltipKey={receptionMetricTooltipKey[key]}
              value={data ? (data[key] ?? 0).toLocaleString() : '0'}
              loading={isLoading}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function renderValue(metric: MetricKey, data: OverviewMetrics | undefined): string {
  if (!data) return '0'
  if (isDurationMetric(metric)) {
    return formatDuration(metric === 'avg_queue_duration_seconds'
      ? data.avg_queue_duration_seconds
      : data.avg_duration_seconds)
  }
  const v = data[metric]
  return typeof v === 'number' ? v.toLocaleString() : '0'
}

function Card({
  labelKey,
  tooltipKey,
  value,
  loading,
}: {
  labelKey: string
  tooltipKey?: string
  value: string
  loading?: boolean
}) {
  const { locale } = useLocaleStore()
  const tooltip = tooltipKey ? t(tooltipKey, locale) : undefined
  return (
    <div className="flex h-24 flex-1 flex-col justify-center gap-2 rounded-[10px] border border-border bg-background px-5 py-4">
      <span className="text-sm text-muted-foreground" title={tooltip}>
        {t(labelKey, locale)}
      </span>
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
