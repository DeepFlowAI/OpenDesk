'use client'

import { useCallback, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRouter, useSearchParams } from 'next/navigation'
import { DateToolbar } from '@/app/components/features/session-reports/date-toolbar'
import { CallOverviewCards } from '@/app/components/features/call-reports/overview-cards'
import { CallReportTabs } from '@/app/components/features/call-reports/report-tabs'
import { CallTrendChartCard } from '@/app/components/features/call-reports/trend-chart'
import { useCallReportsOverview } from '@/service/use-call-reports'
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
  const [dateRangeValid, setDateRangeValid] = useState(true)
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

  const { data: overview, isFetching } = useCallReportsOverview({ start, end })

  const handleRefresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ['call-reports'] })
  }, [queryClient])

  const carriedSearch = useMemo(() => searchParams.toString(), [searchParams])

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        <CallReportTabs active="overall" search={carriedSearch} />
        <DateToolbar
          start={start}
          end={end}
          asOf={overview?.as_of ?? null}
          loading={isFetching || trendLoading || !dateRangeValid}
          onChange={(range) => updateParams(range)}
          onRefresh={handleRefresh}
          onValidityChange={setDateRangeValid}
        />
        <CallOverviewCards start={start} end={end} />
        <CallTrendChartCard
          start={start}
          end={end}
          trend={trend}
          onTrendChange={(nextTrend) => updateParams({ trend: nextTrend })}
          onLoadingChange={setTrendLoading}
        />
      </div>
    </div>
  )
}
