'use client'

import { useCallback, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useOverallSummary } from '@/service/use-session-reports-overall'
import { DateToolbar } from '@/app/components/features/session-reports/date-toolbar'
import { ReportTabs } from '@/app/components/features/session-reports/report-tabs'
import { OverallOverview } from '@/app/components/features/session-reports/overall/overall-overview'
import { OverallTrend } from '@/app/components/features/session-reports/overall/overall-trend'
import { OverallExportButton } from '@/app/components/features/session-reports/overall/overall-export-button'
import { orderedGroups } from '@/app/components/features/session-reports/overall/group-utils'
import type { TrendType } from '@/models/session-report'

function todayIsoDate(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const VALID_TRENDS: TrendType[] = ['half_hour', 'hour', 'day', 'week', 'month']

export default function SessionReportsOverallPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [dateRangeValid, setDateRangeValid] = useState(true)
  const [trendLoading, setTrendLoading] = useState(false)

  const today = todayIsoDate()
  const start = searchParams.get('start') || today
  const end = searchParams.get('end') || today
  const trendParam = searchParams.get('trend')
  const trend: TrendType = (VALID_TRENDS.includes(trendParam as TrendType) ? trendParam : 'hour') as TrendType

  const updateParams = useCallback(
    (next: { start?: string; end?: string; trend?: TrendType }) => {
      const p = new URLSearchParams(searchParams.toString())
      if (next.start) p.set('start', next.start)
      if (next.end) p.set('end', next.end)
      if (next.trend) p.set('trend', next.trend)
      router.replace(`/workspace/records/session-reports?${p.toString()}`)
    },
    [router, searchParams]
  )

  const { data: summary, refetch: refetchSummary, isFetching, isLoading } = useOverallSummary({ start, end })

  const groups = useMemo(() => orderedGroups(summary?.metrics ?? []), [summary])

  const handleRefresh = useCallback(() => {
    refetchSummary()
  }, [refetchSummary])

  const carriedSearch = useMemo(() => searchParams.toString(), [searchParams])

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        <ReportTabs active="overall" search={carriedSearch} />
        <DateToolbar
          start={start}
          end={end}
          asOf={summary?.as_of ?? null}
          loading={isFetching}
          exportAction={
            <OverallExportButton
              params={{ start, end, trend }}
              disabled={!dateRangeValid || isFetching || trendLoading}
            />
          }
          onChange={(r) => updateParams(r)}
          onRefresh={handleRefresh}
          onValidityChange={setDateRangeValid}
        />
        <OverallOverview
          metrics={summary?.metrics ?? []}
          distributions={summary?.distributions ?? []}
          loading={isLoading}
        />
        <OverallTrend
          start={start}
          end={end}
          trend={trend}
          groups={groups}
          distributions={summary?.distributions ?? []}
          onTrendChange={(t) => updateParams({ trend: t })}
          onLoadingChange={setTrendLoading}
        />
      </div>
    </div>
  )
}
