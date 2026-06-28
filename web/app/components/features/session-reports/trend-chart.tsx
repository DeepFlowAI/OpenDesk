'use client'

import { useEffect, useMemo, useState } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { useSessionReportsTrend } from '@/service/use-session-reports'
import type { MetricKey, TrendBucket, TrendResponse, TrendType } from '@/models/session-report'
import { formatDuration } from '@/utils/format-duration'
import { formatTrendXLabel, shouldShowTrendXLabel } from '@/utils/trend-chart-x-axis'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import { isDurationMetric, metricLabelKey, trendTypeLabelKey, TREND_TYPES, visibleMetricKeys } from './types'
import { TrendTable } from './trend-table'

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

function metricValue(bucket: TrendBucket, metric: MetricKey): number {
  switch (metric) {
    case 'avg_duration_seconds':
      return bucket.metrics.avg_duration_seconds ?? 0
    case 'avg_queue_duration_seconds':
      return bucket.metrics.avg_queue_duration_seconds ?? 0
    case 'offline_message_count':
      return bucket.metrics.offline_message_count ?? 0
    default:
      return bucket.metrics[metric]
  }
}

function niceMax(rawMax: number): number {
  if (rawMax <= 0) return 40 // fallback display range
  const pow = Math.pow(10, Math.floor(Math.log10(rawMax)))
  const norm = rawMax / pow
  let nice: number
  if (norm <= 1) nice = 1
  else if (norm <= 2) nice = 2
  else if (norm <= 5) nice = 5
  else nice = 10
  return nice * pow
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
  const [metric, setMetric] = useState<MetricKey>('session_count')
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

  useEffect(() => {
    if (!metricKeys.includes(metric)) {
      setMetric('session_count')
    }
  }, [metric, metricKeys])

  const buckets = data?.buckets ?? []
  const isEmpty = !isLoading && buckets.every((b) => metricValue(b, metric) === 0)

  const maxValue = useMemo(() => {
    const max = Math.max(0, ...buckets.map((b) => metricValue(b, metric)))
    return niceMax(max)
  }, [buckets, metric])

  const yLabels = useMemo(() => {
    // 5 ticks top→bottom: max, 75%, 50%, 25%, 0
    return [1, 0.75, 0.5, 0.25, 0].map((p) => {
      const v = maxValue * p
      return isDurationMetric(metric) ? formatDuration(v) : Math.round(v).toLocaleString()
    })
  }, [maxValue, metric])

  const chartTitle = t('ws.records.sessionReports.trend.chartTitle', locale)
    .replace('{metric}', t(metricLabelKey[metric], locale))
    .replace('{type}', t(trendTypeLabelKey[trend], locale))

  return (
    <div className="rounded-[10px] border border-border bg-background p-6">
      {/* Header row */}
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">
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

      {/* Chart area */}
      {isEmpty ? (
        <div className="flex h-[236px] items-center justify-center text-sm text-muted-foreground">
          {t('ws.records.sessionReports.trend.empty', locale)}
        </div>
      ) : (
        <div className="flex h-[236px]">
          {/* Y labels */}
          <div className="flex h-full w-10 flex-col justify-between pb-5 text-right">
            {yLabels.map((label, i) => (
              <span key={i} className="text-[11px] text-[#999999]">{label}</span>
            ))}
          </div>
          {/* Bars area */}
          <div className="flex flex-1 flex-col">
            <div className="flex h-[200px] items-end gap-1.5 px-2">
              {buckets.map((b, i) => {
                const v = metricValue(b, metric)
                const h = maxValue > 0 ? (v / maxValue) * 100 : 0
                return (
                  <div
                    key={i}
                    className="group relative flex h-full flex-1 items-end"
                    title={`${b.label} · ${
                      isDurationMetric(metric) ? formatDuration(v) : v
                    }`}
                  >
                    <div
                      style={{ height: `${h}%` }}
                      className="w-full rounded-sm bg-foreground transition-all"
                    />
                  </div>
                )
              })}
            </div>
            <div
              className={cn(
                'flex h-6 gap-1.5 px-2 pt-1 text-[#999999]',
                trend === 'half_hour' ? 'text-[9px]' : trend === 'hour' ? 'text-[10px]' : 'text-[11px]',
              )}
            >
              {buckets.map((b, index) => (
                <div
                  key={`x-${b.label}-${index}`}
                  className="flex-1 truncate text-center leading-none"
                >
                  {shouldShowTrendXLabel(index, buckets.length, trend)
                    ? formatTrendXLabel(b.label, index, trend)
                    : ''}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Metric tabs */}
      <div className="mt-4 flex flex-wrap justify-center gap-1 border-t border-border pt-4">
        {metricKeys.map((key) => {
          const active = key === metric
          return (
            <button
              key={key}
              type="button"
              onClick={() => setMetric(key)}
              className={cn(
                'h-8 rounded-lg px-3.5 text-sm transition-colors',
                active
                  ? 'bg-foreground font-semibold text-background'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              {t(metricLabelKey[key], locale)}
            </button>
          )
        })}
      </div>

      {/* Trend detail table */}
      <div className="mt-6">
        <div className="mb-3 text-sm font-semibold text-foreground">
          {t('ws.records.sessionReports.trend.detail', locale)}
        </div>
        <TrendTable buckets={buckets} showBusinessMetrics={includeBusinessMetrics} />
      </div>
    </div>
  )
}
