'use client'

import { useCallback, useMemo, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { DateToolbar } from '@/app/components/features/session-reports/date-toolbar'
import { CallEmployeeDetailHeader } from '@/app/components/features/call-reports/employee-detail-header'
import { CallOverviewCards } from '@/app/components/features/call-reports/overview-cards'
import { CallReportTabs } from '@/app/components/features/call-reports/report-tabs'
import { CallTrendChartCard } from '@/app/components/features/call-reports/trend-chart'
import { useLocaleStore } from '@/context/locale-store'
import { useCallReportsEmployees, useCallReportsOverview } from '@/service/use-call-reports'
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

export default function CallReportsEmployeeDetailPage() {
  const params = useParams<{ employeeId: string }>()
  const employeeId = parseInt(params.employeeId, 10)
  const router = useRouter()
  const searchParams = useSearchParams()
  const { locale } = useLocaleStore()
  const [dateRangeValid, setDateRangeValid] = useState(true)
  const [trendLoading, setTrendLoading] = useState(false)

  const today = todayIsoDate()
  const start = searchParams.get('start') || today
  const end = searchParams.get('end') || today
  const trendParam = searchParams.get('trend')
  const trend: TrendType = (VALID_TRENDS.includes(trendParam as TrendType) ? trendParam : 'hour') as TrendType

  const carriedSearch = useMemo(() => searchParams.toString(), [searchParams])
  const validEmployeeId = Number.isFinite(employeeId)

  const { data: employeesData, isLoading: employeeLoading } = useCallReportsEmployees({
    start,
    end,
    per_page: 100,
    enabled: validEmployeeId,
  })
  const employee = employeesData?.items.find((row) => row.employee.id === employeeId)?.employee

  const updateParams = useCallback(
    (next: { start?: string; end?: string; trend?: TrendType }) => {
      const params = new URLSearchParams(searchParams.toString())
      if (next.start) params.set('start', next.start)
      if (next.end) params.set('end', next.end)
      if (next.trend) params.set('trend', next.trend)
      router.replace(`/workspace/records/call-reports/employees/${employeeId}?${params.toString()}`)
    },
    [employeeId, router, searchParams]
  )

  const { data: overview, refetch, isFetching } = useCallReportsOverview({
    start,
    end,
    employee_id: validEmployeeId ? employeeId : undefined,
    enabled: validEmployeeId,
  })

  if (!validEmployeeId) {
    return (
      <div className="flex h-full flex-col overflow-auto">
        <div className="flex flex-col gap-5 p-6">
          <CallReportTabs active="employees" search={carriedSearch} />
          <div className="text-sm text-muted-foreground">
            {t('ws.records.callReports.employees.notFound', locale)}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        <CallReportTabs active="employees" search={carriedSearch} />
        <DateToolbar
          start={start}
          end={end}
          asOf={overview?.as_of ?? null}
          loading={isFetching || trendLoading || !dateRangeValid}
          onChange={(range) => updateParams(range)}
          onRefresh={() => refetch()}
          onValidityChange={setDateRangeValid}
        />
        {employee ? (
          <>
            <CallEmployeeDetailHeader employee={employee} carriedSearch={carriedSearch} />
            <CallOverviewCards start={start} end={end} employeeId={employeeId} />
            <CallTrendChartCard
              start={start}
              end={end}
              trend={trend}
              onTrendChange={(nextTrend) => updateParams({ trend: nextTrend })}
              employeeId={employeeId}
              onLoadingChange={setTrendLoading}
            />
          </>
        ) : employeeLoading ? (
          <div className="text-sm text-muted-foreground">
            {t('ws.records.sessionReports.common.loading', locale)}
          </div>
        ) : (
          <div className="text-sm text-muted-foreground">
            {t('ws.records.callReports.employees.notFound', locale)}
          </div>
        )}
      </div>
    </div>
  )
}
