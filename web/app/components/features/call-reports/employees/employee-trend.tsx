'use client'

import { useEffect, useMemo, useState } from 'react'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import type { TrendType } from '@/models/call-report'
import { useCallAgentTrend } from '@/service/use-call-agent-reports'
import { t } from '@/utils/i18n'
import { TREND_TYPES, trendTypeLabelKey } from '../types'
import { isCallTrendEmpty, type CallTrendChartBucket, type CallTrendChartMetric } from '../overall/build-call-trend-chart-option'
import { CallMultiMetricTrendChart } from '../overall/call-multi-metric-trend-chart'
import { callGroupLabel, callMetricLabel } from '../overall/metric-format'
import { CallOverallDetailTable } from '../overall/overall-detail-table'

export function CallEmployeeTrend({ employeeId, start, end, trend, groups, enabled = true,
  summaryLoading = false, onTrendChange, onLoadingChange }: {
  employeeId: number; start: string; end: string; trend: TrendType; groups: string[]
  enabled?: boolean; summaryLoading?: boolean; onTrendChange: (trend: TrendType) => void
  onLoadingChange?: (loading: boolean) => void
}) {
  const { locale } = useLocaleStore()
  const [group, setGroup] = useState('')
  const selectedGroup = groups.includes(group) ? group : groups[0] ?? ''
  useEffect(() => { if (selectedGroup !== group) setGroup(selectedGroup) }, [group, selectedGroup])
  const query = useCallAgentTrend({ employeeId, start, end, trend, group: selectedGroup,
    enabled: enabled && Boolean(selectedGroup) })
  const loading = summaryLoading || query.isLoading || query.isPlaceholderData
  useEffect(() => { onLoadingChange?.(query.isFetching) }, [onLoadingChange, query.isFetching])
  const descriptors = useMemo(() => loading || query.data?.group !== selectedGroup ? [] : query.data?.metrics ?? [], [loading, query.data, selectedGroup])
  const buckets = useMemo(() => loading || query.data?.group !== selectedGroup ? [] : query.data?.buckets ?? [], [loading, query.data, selectedGroup])
  const chartMetrics = useMemo<CallTrendChartMetric[]>(() => descriptors.map((metric) => ({
    key: metric.key, name: callMetricLabel(metric.key, locale), format: metric.format, level: metric.level,
  })), [descriptors, locale])
  const chartBuckets = useMemo<CallTrendChartBucket[]>(() => buckets.map((bucket) => ({ label: bucket.label, metrics: bucket.metrics })), [buckets])
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-foreground">{t('ws.records.callReports.overall.trend.title', locale)}</h2>
        <div className="flex flex-wrap gap-1">{TREND_TYPES.map((type) => <button key={type} type="button" onClick={() => onTrendChange(type)}
          className={cn('h-8 rounded-lg px-3 text-xs transition-colors', type === trend ? 'bg-muted font-semibold text-foreground' : 'border border-border text-muted-foreground hover:text-foreground')}>
          {t(trendTypeLabelKey[type], locale)}</button>)}</div>
      </div>
      <div className="flex flex-wrap gap-1">{groups.map((item) => <button key={item} type="button" onClick={() => setGroup(item)}
        className={cn('h-8 rounded-lg px-3.5 text-sm transition-colors', item === selectedGroup ? 'bg-primary font-semibold text-primary-foreground' : 'border border-border text-muted-foreground hover:text-foreground')}>
        {callGroupLabel(item, locale)}</button>)}</div>
      {query.isError ? <TrendState messageKey="ws.records.callReports.overall.trend.loadFailed" onRetry={() => query.refetch()} />
        : loading ? <div className="h-[340px] animate-pulse rounded-lg bg-muted" aria-busy="true" />
          : isCallTrendEmpty(chartMetrics, chartBuckets) ? <TrendState messageKey="ws.records.callReports.employees.trendEmpty" />
            : <CallMultiMetricTrendChart metrics={chartMetrics} buckets={chartBuckets} trend={trend} locale={locale}
              axisLabels={{ count: t('ws.records.callReports.overall.trend.axisCount', locale), duration: t('ws.records.callReports.overall.trend.axisDuration', locale), percent: t('ws.records.callReports.overall.trend.axisPercent', locale) }} />}
      {!query.isError && !loading ? <div className="space-y-3 pt-2">
        <h3 className="text-sm font-semibold text-foreground">{t('ws.records.callReports.overall.trend.detail', locale)}</h3>
        <CallOverallDetailTable buckets={buckets} descriptors={descriptors} />
      </div> : null}
    </section>
  )
}

function TrendState({ messageKey, onRetry }: { messageKey: string; onRetry?: () => void }) {
  const { locale } = useLocaleStore()
  return <div className="flex h-[340px] flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
    <span>{t(messageKey, locale)}</span>
    {onRetry ? <button type="button" onClick={onRetry} className="h-9 rounded-md bg-primary px-4 text-primary-foreground">{t('ws.records.callReports.overall.retry', locale)}</button> : null}
  </div>
}
