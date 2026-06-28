'use client'

import { useEffect, useMemo, useState } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import type { TrendType } from '@/models/session-report'
import type { MetricDistribution } from '@/models/session-report-overall'
import { useOverallTrend } from '@/service/use-session-reports-overall'
import { TREND_TYPES, trendTypeLabelKey } from '../types'
import {
  isTrendChartEmpty,
  type TrendChartBucket,
  type TrendChartMetric,
} from '../multi-metric-trend-chart/build-trend-chart-option'
import { MultiMetricTrendChart } from '../multi-metric-trend-chart/multi-metric-trend-chart'
import { OverallDetailTable } from './overall-detail-table'
import { groupLabelKey, metricDisplayLabel } from './metric-format'

type Props = {
  start: string
  end: string
  trend: TrendType
  /** Ordered group keys from the summary registry. */
  groups: string[]
  distributions?: MetricDistribution[]
  onTrendChange: (trend: TrendType) => void
  onLoadingChange?: (loading: boolean) => void
}

export function OverallTrend({
  start,
  end,
  trend,
  groups,
  distributions = [],
  onTrendChange,
  onLoadingChange,
}: Props) {
  const { locale } = useLocaleStore()
  const [group, setGroup] = useState<string>('')

  useEffect(() => {
    if (groups.length === 0) return
    if (!groups.includes(group)) setGroup(groups[0])
  }, [groups, group])

  const { data, isLoading, isFetching } = useOverallTrend({
    start,
    end,
    trend,
    group,
    enabled: !!group,
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
        name: metricDisplayLabel(d.key, locale, distributions),
        format: d.format,
        level: d.level,
      })),
    [descriptors, distributions, locale],
  )

  const chartBuckets = useMemo<TrendChartBucket[]>(
    () =>
      buckets.map((b) => ({
        label: b.label,
        metrics: b.metrics.map((m) => ({
          key: m.key,
          value: m.value,
          format: m.format,
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
    group: t(groupLabelKey(group), locale),
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

      {groups.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-1">
          {groups.map((g) => {
            const active = g === group
            return (
              <button
                key={g}
                type="button"
                onClick={() => setGroup(g)}
                className={cn(
                  'h-8 rounded-lg px-3.5 text-sm transition-colors',
                  active
                    ? 'bg-muted font-semibold text-foreground'
                    : 'border border-border bg-background text-muted-foreground hover:text-foreground'
                )}
              >
                {t(groupLabelKey(g), locale)}
              </button>
            )
          })}
        </div>
      )}

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
        <OverallDetailTable
          buckets={buckets}
          descriptors={descriptors}
          distributions={distributions}
        />
      </div>
    </div>
  )
}
