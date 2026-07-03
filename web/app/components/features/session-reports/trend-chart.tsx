'use client'

import { useEffect, useMemo } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { useSessionReportsTrend } from '@/service/use-session-reports'
import type { MetricKey, TrendBucket, TrendResponse, TrendType } from '@/models/session-report'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import { isDurationMetric, metricLabelKey, trendTypeLabelKey, TREND_TYPES, visibleMetricKeys } from './types'
import { TrendTable } from './trend-table'
import {
  isTrendChartEmpty,
  type TrendChartBucket,
  type TrendChartMetric,
} from './multi-metric-trend-chart/build-trend-chart-option'
import { MultiMetricTrendChart } from './multi-metric-trend-chart/multi-metric-trend-chart'

type Props = {
  start: string
  end: string
  trend: TrendType
  onTrendChange: (trend: TrendType) => void
  employeeId?: number
  onLoadingChange?: (loading: boolean) => void
  data?: TrendResponse
  loading?: boolean
  fetch?: boolean
}

function metricValue(bucket: TrendBucket, metric: MetricKey): number | null {
  const value = bucket.metrics[metric]
  return typeof value === 'number' ? value : null
}

function metricFormat(metric: MetricKey): TrendChartMetric['format'] {
  return isDurationMetric(metric) ? 'duration_seconds' : 'integer'
}

export function TrendChartCard({
  start,
  end,
  trend,
  onTrendChange,
  employeeId,
  onLoadingChange,
  data: externalData,
  loading,
  fetch = true,
}: Props) {
  const { locale } = useLocaleStore()
  const trendQuery = useSessionReportsTrend({
    start,
    end,
    trend,
    employee_id: employeeId,
    enabled: fetch && externalData === undefined,
  })
  const data = externalData ?? trendQuery.data
  const isLoading = loading ?? trendQuery.isLoading
  const isFetching = loading ?? trendQuery.isFetching
  const includeBusinessMetrics = employeeId === undefined
  const canViewOfflineMessages = data?.buckets[0]?.metrics.can_view_offline_messages ?? true
  const metricKeys = useMemo(() => visibleMetricKeys({
    includeBusinessMetrics,
    canViewOfflineMessages,
  }), [canViewOfflineMessages, includeBusinessMetrics])

  useEffect(() => {
    onLoadingChange?.(isFetching)
  }, [isFetching, onLoadingChange])

  const buckets = data?.buckets ?? []
  const chartMetrics = useMemo<TrendChartMetric[]>(
    () =>
      metricKeys.map((key) => ({
        key,
        name: t(metricLabelKey[key], locale),
        format: metricFormat(key),
        level: 'primary',
      })),
    [locale, metricKeys],
  )
  const chartBuckets = useMemo<TrendChartBucket[]>(
    () =>
      buckets.map((bucket) => ({
        label: bucket.label,
        metrics: metricKeys.map((key) => ({
          key,
          value: metricValue(bucket, key),
          format: metricFormat(key),
        })),
      })),
    [buckets, metricKeys],
  )
  const axisLabels = useMemo(
    () => ({
      count: t('ws.records.sessionReports.trend.axisCount', locale),
      duration: t('ws.records.sessionReports.trend.axisDuration', locale),
      percent: t('ws.records.sessionReports.trend.axisPercent', locale),
    }),
    [locale],
  )
  const isEmpty = !isLoading && isTrendChartEmpty(chartMetrics, chartBuckets)

  const chartTitle = t('ws.records.sessionReports.trend.basicChartTitle', locale, {
    type: t(trendTypeLabelKey[trend], locale),
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">
          {t('ws.records.sessionReports.trend.title', locale)}
        </h2>
        <div className="flex gap-1">
          {TREND_TYPES.map((type) => {
            const active = type === trend
            return (
              <button
                key={type}
                type="button"
                onClick={() => onTrendChange(type)}
                className={cn(
                  'h-8 rounded-lg px-3 text-xs transition-colors',
                  active
                    ? 'bg-muted font-semibold text-foreground'
                    : 'border border-border bg-background text-muted-foreground hover:text-foreground'
                )}
              >
                {t(trendTypeLabelKey[type], locale)}
              </button>
            )
          })}
        </div>
      </div>

      <div className="mb-3 text-sm font-semibold text-foreground">{chartTitle}</div>

      {isEmpty ? (
        <div className="flex h-[320px] items-center justify-center text-sm text-muted-foreground">
          {t('ws.records.sessionReports.trend.empty', locale)}
        </div>
      ) : (
        <MultiMetricTrendChart
          metrics={chartMetrics}
          buckets={chartBuckets}
          trend={trend}
          axisLabels={axisLabels}
        />
      )}

      <div className="mt-6">
        <div className="mb-3 text-sm font-semibold text-foreground">
          {t('ws.records.sessionReports.trend.detail', locale)}
        </div>
        <TrendTable buckets={buckets} showBusinessMetrics={includeBusinessMetrics} />
      </div>
    </div>
  )
}
