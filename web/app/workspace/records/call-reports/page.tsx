'use client'

import { useCallback, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRouter, useSearchParams } from 'next/navigation'
import { DateToolbar } from '@/app/components/features/session-reports/date-toolbar'
import { CallReportTabs } from '@/app/components/features/call-reports/report-tabs'
import { CallReportExportButton } from '@/app/components/features/call-reports/export-button'
import { CallOverallOverview } from '@/app/components/features/call-reports/overall/overall-overview'
import { CallOverallTrend } from '@/app/components/features/call-reports/overall/overall-trend'
import {
  CallHistoryUnavailable,
  CallReportNotices,
} from '@/app/components/features/call-reports/overall/report-notices'
import { orderedCallGroups } from '@/app/components/features/call-reports/overall/group-utils'
import {
  callOverallKeys,
  useCallOverallSummary,
} from '@/service/use-call-reports-overall'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { TrendType } from '@/models/call-report'

function todayIsoDate(): string {
  const date = new Date()
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const VALID_TRENDS: TrendType[] = ['half_hour', 'hour', 'day', 'week', 'month']

export default function CallReportsOverallPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const queryClient = useQueryClient()
  const { locale } = useLocaleStore()
  const [trendLoading, setTrendLoading] = useState(false)

  const today = todayIsoDate()
  const start = searchParams.get('start') || today
  const end = searchParams.get('end') || today
  const trendParam = searchParams.get('trend')
  const trend: TrendType = (VALID_TRENDS.includes(trendParam as TrendType) ? trendParam : 'hour') as TrendType

  const updateParams = useCallback(
    (next: { start?: string; end?: string; trend?: TrendType }) => {
      const params = new URLSearchParams(searchParams.toString())
      if (next.start) params.set('start', next.start)
      if (next.end) params.set('end', next.end)
      if (next.trend) params.set('trend', next.trend)
      router.replace(`/workspace/records/call-reports?${params.toString()}`)
    },
    [router, searchParams]
  )

  const dateRangeValid = isValidRange(start, end)
  const summaryQuery = useCallOverallSummary({ start, end, enabled: dateRangeValid })
  const summary = summaryQuery.data
  const groups = useMemo(() => orderedCallGroups(summary?.metrics ?? []), [summary])
  const totalCalls = summary?.metrics.find((metric) => metric.key === 'call_count')?.value ?? 0
  const coverageAvailable = summary?.coverage.status !== 'unavailable'

  const handleRefresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: callOverallKeys.all })
  }, [queryClient])

  const carriedSearch = useMemo(() => searchParams.toString(), [searchParams])

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        <CallReportTabs active="overall" search={carriedSearch} />
        <DateToolbar
          start={start}
          end={end}
          asOf={summary?.as_of ?? null}
          loading={summaryQuery.isFetching || trendLoading || !dateRangeValid}
          onChange={(range) => updateParams(range)}
          onRefresh={handleRefresh}
          exportAction={<CallReportExportButton
            params={{ kind: 'overall', start, end, trend }}
            disabled={!dateRangeValid || summaryQuery.isLoading || (summaryQuery.isError && !summary)}
          />}
        />
        {summaryQuery.isError && !summary ? (
          <SummaryError onRetry={() => summaryQuery.refetch()} />
        ) : (
          <>
            {summary && summary.coverage.status !== 'unavailable' ? (
              <CallReportNotices
                coverage={summary.coverage}
                dataQuality={summary.data_quality}
              />
            ) : null}
            {summary?.coverage.status === 'unavailable' ? (
              <CallHistoryUnavailable effectiveAt={summary.coverage.effective_at} />
            ) : (
              <>
                {!summaryQuery.isLoading && totalCalls === 0 ? (
                  <div className="rounded-lg border border-dashed border-border bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
                    {t('ws.records.callReports.overall.empty', locale)}
                  </div>
                ) : null}
                <CallOverallOverview
                  metrics={summary?.metrics ?? []}
                  distributions={summary?.distributions ?? []}
                  loading={summaryQuery.isLoading}
                />
                <CallOverallTrend
                  start={start}
                  end={end}
                  trend={trend}
                  groups={groups}
                  enabled={dateRangeValid && coverageAvailable && !summaryQuery.isLoading}
                  summaryLoading={summaryQuery.isLoading}
                  onTrendChange={(nextTrend) => updateParams({ trend: nextTrend })}
                  onLoadingChange={setTrendLoading}
                />
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function isValidRange(start: string, end: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end)) return false
  if (start > end) return false
  const startDate = new Date(`${start}T00:00:00Z`)
  const endDate = new Date(`${end}T00:00:00Z`)
  return (endDate.getTime() - startDate.getTime()) / 86_400_000 < 366
}

function SummaryError({ onRetry }: { onRetry: () => void }) {
  const { locale } = useLocaleStore()
  return (
    <div className="flex min-h-[320px] flex-col items-center justify-center gap-3 rounded-lg border border-border">
      <p className="text-sm text-muted-foreground">
        {t('ws.records.callReports.overall.loadFailed', locale)}
      </p>
      <button type="button" onClick={onRetry} className="h-9 rounded-md bg-primary px-4 text-sm text-primary-foreground">
        {t('ws.records.callReports.overall.retry', locale)}
      </button>
    </div>
  )
}
