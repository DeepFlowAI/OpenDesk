'use client'

import { useEffect, useMemo } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { useSessionReportQueueTrend } from '@/service/use-session-reports'
import { t } from '@/utils/i18n'
import type {
  QueueMetricGroup,
  QueueTrendBucket,
  QueueTrendDescriptor,
  QueueType,
  TrendType,
} from '@/models/session-report'
import { TREND_TYPES, trendTypeLabelKey } from './types'
import {
  isTrendChartEmpty,
  type TrendChartBucket,
  type TrendChartMetric,
} from './multi-metric-trend-chart/build-trend-chart-option'
import { MultiMetricTrendChart } from './multi-metric-trend-chart/multi-metric-trend-chart'
import {
  formatQueueMetricValue,
  QUEUE_METRIC_GROUPS,
  queueGroupLabelKey,
  queueMetricLabelKey,
} from './queue-types'

type Props = {
  start: string
  end: string
  trend: TrendType
  group: QueueMetricGroup
  queueType: QueueType
  queueId: number
  onTrendChange: (trend: TrendType) => void
  onGroupChange: (group: QueueMetricGroup) => void
  onLoadingChange?: (loading: boolean) => void
}

export function QueueTrend({
  start,
  end,
  trend,
  group,
  queueType,
  queueId,
  onTrendChange,
  onGroupChange,
  onLoadingChange,
}: Props) {
  const { locale } = useLocaleStore()

  const { data, isLoading, isFetching } = useSessionReportQueueTrend({
    start,
    end,
    trend,
    group,
    queue_type: queueType,
    queue_id: queueId,
  })

  useEffect(() => {
    onLoadingChange?.(isFetching)
  }, [isFetching, onLoadingChange])

  const descriptors = useMemo(() => data?.metrics ?? [], [data])
  const buckets = useMemo(() => data?.buckets ?? [], [data])

  const chartMetrics = useMemo<TrendChartMetric[]>(
    () =>
      descriptors.map((d) => ({
        key: d.key,
        name: t(queueMetricLabelKey[d.key], locale),
        format: d.format,
        level: d.level,
      })),
    [descriptors, locale],
  )

  const chartBuckets = useMemo<TrendChartBucket[]>(
    () =>
      buckets.map((bucket) => ({
        label: bucket.label,
        metrics: bucket.metrics.map((metric) => ({
          key: metric.key,
          value: metric.value,
          format: metric.format,
        })),
      })),
    [buckets],
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
  const chartTitle = t('ws.records.sessionReports.trend.groupChartTitle', locale, {
    group: t(queueGroupLabelKey[group], locale),
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

      <div className="mb-4 flex flex-wrap gap-1">
        {QUEUE_METRIC_GROUPS.map((item) => {
          const active = item === group
          return (
            <button
              key={item}
              type="button"
              onClick={() => onGroupChange(item)}
              className={cn(
                'h-8 rounded-lg px-3.5 text-sm transition-colors',
                active
                  ? 'bg-muted font-semibold text-foreground'
                  : 'border border-border bg-background text-muted-foreground hover:text-foreground'
              )}
            >
              {t(queueGroupLabelKey[item], locale)}
            </button>
          )
        })}
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
        <QueueTrendTable buckets={buckets} descriptors={descriptors} />
      </div>
    </div>
  )
}

function QueueTrendTable({
  buckets,
  descriptors,
}: {
  buckets: QueueTrendBucket[]
  descriptors: QueueTrendDescriptor[]
}) {
  const { locale } = useLocaleStore()
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <div className="min-w-max">
        <div className="flex h-12 items-center gap-4 bg-[#F8F8F8] px-6 text-xs font-semibold text-muted-foreground">
          <div className="w-[140px] shrink-0">
            {t('ws.records.sessionReports.trend.colTime', locale)}
          </div>
          {descriptors.map((descriptor) => (
            <div key={descriptor.key} className="w-[150px] shrink-0 text-center">
              {t(queueMetricLabelKey[descriptor.key], locale)}
            </div>
          ))}
        </div>
        <div className="max-h-[480px] overflow-auto">
          {buckets.map((bucket) => {
            const valueByKey = new Map(bucket.metrics.map((metric) => [metric.key, metric]))
            return (
              <div
                key={bucket.label}
                className="flex h-[52px] items-center gap-4 border-b border-[#F0F0F0] px-6 text-[13px] text-foreground last:border-b-0"
              >
                <div className="w-[140px] shrink-0">{bucket.label}</div>
                {descriptors.map((descriptor) => {
                  const metric = valueByKey.get(descriptor.key)
                  return (
                    <div key={descriptor.key} className="w-[150px] shrink-0 text-center">
                      {formatQueueMetricValue(metric?.value, descriptor.format)}
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
