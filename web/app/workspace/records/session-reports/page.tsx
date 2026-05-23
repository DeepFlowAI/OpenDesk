'use client'

import { useCallback, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { useSessionReportsOverview } from '@/service/use-session-reports'
import { DateToolbar } from '@/app/components/features/session-reports/date-toolbar'
import { SessionReportExportButton } from '@/app/components/features/session-reports/export-button'
import { OverviewCards } from '@/app/components/features/session-reports/overview-cards'
import { ReportTabs } from '@/app/components/features/session-reports/report-tabs'
import { TrendChartCard } from '@/app/components/features/session-reports/trend-chart'
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

  const { data: overview, refetch: refetchOverview, isFetching } = useSessionReportsOverview({
    start,
    end,
  })

  const handleRefresh = useCallback(() => {
    refetchOverview()
    // Trend hook re-fetches via its own queryKey when refetch is triggered through
    // a global refetcher; for simplicity here we rely on React Query's window-focus
    // refetch. A keyed refetch from a parent ref is a future improvement.
  }, [refetchOverview])

  const carriedSearch = useMemo(() => searchParams.toString(), [searchParams])

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        <ReportTabs active="overall" search={carriedSearch} />
        <DateToolbar
          start={start}
          end={end}
          asOf={overview?.as_of ?? null}
          loading={isFetching}
          exportAction={
            <SessionReportExportButton
              params={{ scope: 'overall', start, end, trend }}
              disabled={!dateRangeValid || isFetching || trendLoading}
            />
          }
          onChange={(r) => updateParams(r)}
          onRefresh={handleRefresh}
          onValidityChange={setDateRangeValid}
        />
        <OverviewCards start={start} end={end} />
        <TrendChartCard
          start={start}
          end={end}
          trend={trend}
          onTrendChange={(t) => updateParams({ trend: t })}
          onLoadingChange={setTrendLoading}
        />
      </div>
    </div>
  )
}
