'use client'

import { useCallback, useMemo, useState } from 'react'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { DateToolbar } from '@/app/components/features/session-reports/date-toolbar'
import { EmployeeDetailHeader } from '@/app/components/features/session-reports/employee-detail-header'
import { SessionReportExportButton } from '@/app/components/features/session-reports/export-button'
import { OverviewCards } from '@/app/components/features/session-reports/overview-cards'
import { ReportTabs } from '@/app/components/features/session-reports/report-tabs'
import { TrendChartCard } from '@/app/components/features/session-reports/trend-chart'
import { useLocaleStore } from '@/context/locale-store'
import { useSessionReportEmployeeDetail, useSessionReportEmployeeTrend } from '@/service/use-session-reports'
import { t } from '@/utils/i18n'
import type { TrendType } from '@/models/session-report'

function todayIsoDate(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const VALID_TRENDS: TrendType[] = ['half_hour', 'hour', 'day', 'week', 'month']

export default function EmployeeDetailPage() {
  const params = useParams<{ employeeId: string }>()
  const employeeId = parseInt(params.employeeId, 10)
  const router = useRouter()
  const searchParams = useSearchParams()
  const { locale } = useLocaleStore()
  const [dateRangeValid, setDateRangeValid] = useState(true)

  const today = todayIsoDate()
  const start = searchParams.get('start') || today
  const end = searchParams.get('end') || today
  const trendParam = searchParams.get('trend')
  const trend: TrendType = (VALID_TRENDS.includes(trendParam as TrendType) ? trendParam : 'hour') as TrendType
  const validEmployeeId = Number.isFinite(employeeId)

  const updateParams = useCallback(
    (next: { start?: string; end?: string; trend?: TrendType }) => {
      const p = new URLSearchParams(searchParams.toString())
      if (next.start) p.set('start', next.start)
      if (next.end) p.set('end', next.end)
      if (next.trend) p.set('trend', next.trend)
      router.replace(`/workspace/records/session-reports/employees/${employeeId}?${p.toString()}`)
    },
    [router, searchParams, employeeId]
  )

  const detailQuery = useSessionReportEmployeeDetail({
    start,
    end,
    employee_id: employeeId,
    enabled: validEmployeeId && dateRangeValid,
  })
  const trendQuery = useSessionReportEmployeeTrend({
    start,
    end,
    trend,
    employee_id: employeeId,
    enabled: validEmployeeId && dateRangeValid && !!detailQuery.data,
  })
  const detail = detailQuery.data
  const employee = detail?.employee

  const carriedSearch = useMemo(() => searchParams.toString(), [searchParams])
  const loading = detailQuery.isFetching || trendQuery.isFetching
  const inaccessible = !validEmployeeId || detailQuery.isError

  const handleRefresh = () => {
    if (!validEmployeeId) return
    detailQuery.refetch()
    if (detailQuery.data) trendQuery.refetch()
  }

  if (inaccessible) {
    return (
      <div className="flex h-full flex-col overflow-auto">
        <div className="flex flex-col gap-5 p-6">
          <ReportTabs active="employees" search={carriedSearch} />
          <DateToolbar
            start={start}
            end={end}
            asOf={null}
            loading={loading}
            onChange={(r) => updateParams(r)}
            onRefresh={handleRefresh}
            onValidityChange={setDateRangeValid}
          />
          <div className="text-sm text-muted-foreground">
            {t('ws.records.sessionReports.employees.notFound', locale)}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        <ReportTabs active="employees" search={carriedSearch} />
        <DateToolbar
          start={start}
          end={end}
          asOf={detail?.as_of ?? null}
          loading={loading}
          exportAction={
            <SessionReportExportButton
              params={{ scope: 'employee', start, end, trend, employee_id: employeeId }}
              disabled={!dateRangeValid || loading || !employee}
            />
          }
          onChange={(r) => updateParams(r)}
          onRefresh={handleRefresh}
          onValidityChange={setDateRangeValid}
        />
        {employee ? (
          <EmployeeDetailHeader employee={employee} carriedSearch={carriedSearch} />
        ) : (
          <div className="text-sm text-muted-foreground">
            {t('ws.records.sessionReports.common.loading', locale)}
          </div>
        )}
        <OverviewCards
          start={start}
          end={end}
          employeeId={employeeId}
          data={detail?.metrics}
          loading={detailQuery.isLoading}
          fetch={false}
        />
        <TrendChartCard
          start={start}
          end={end}
          trend={trend}
          onTrendChange={(t) => updateParams({ trend: t })}
          employeeId={employeeId}
          data={trendQuery.data}
          loading={trendQuery.isLoading}
          fetch={false}
        />
      </div>
    </div>
  )
}
