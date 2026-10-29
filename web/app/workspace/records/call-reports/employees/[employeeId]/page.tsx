'use client'

import { useCallback, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { HTTPError } from 'ky'
import { useParams, useRouter, useSearchParams } from 'next/navigation'
import { CallEmployeeDetailHeader } from '@/app/components/features/call-reports/employee-detail-header'
import { CallEmployeeOverview, EMPLOYEE_GROUP_ORDER } from '@/app/components/features/call-reports/employees/employee-overview'
import { CallEmployeeHistoryUnavailable, CallEmployeeReportNotices } from '@/app/components/features/call-reports/employees/employee-report-notices'
import { CallEmployeeTrend } from '@/app/components/features/call-reports/employees/employee-trend'
import { CallReportTabs } from '@/app/components/features/call-reports/report-tabs'
import { CallReportExportButton } from '@/app/components/features/call-reports/export-button'
import { DateToolbar } from '@/app/components/features/session-reports/date-toolbar'
import { useLocaleStore } from '@/context/locale-store'
import type { TrendType } from '@/models/call-report'
import { callAgentKeys, useCallAgentSummary } from '@/service/use-call-agent-reports'
import { t } from '@/utils/i18n'

const VALID_TRENDS: TrendType[] = ['half_hour', 'hour', 'day', 'week', 'month']

export default function CallReportsEmployeeDetailPage() {
  const params = useParams<{ employeeId: string }>()
  const router = useRouter()
  const searchParams = useSearchParams()
  const queryClient = useQueryClient()
  const [trendLoading, setTrendLoading] = useState(false)
  const employeeId = Number.parseInt(params.employeeId, 10)
  const validEmployee = Number.isFinite(employeeId) && employeeId > 0
  const today = todayIsoDate()
  const start = searchParams.get('start') || today
  const end = searchParams.get('end') || today
  const trendParam = searchParams.get('trend')
  const trend: TrendType = VALID_TRENDS.includes(trendParam as TrendType) ? trendParam as TrendType : 'hour'
  const dateRangeValid = isValidRange(start, end)
  const summaryQuery = useCallAgentSummary({ employeeId, start, end, enabled: validEmployee && dateRangeValid })
  const summary = summaryQuery.data
  const carriedSearch = useMemo(() => searchParams.toString(), [searchParams])
  const groups = EMPLOYEE_GROUP_ORDER.filter((group) => summary?.metrics.some((metric) => metric.group === group && metric.available))
  const errorMessageKey = summaryQuery.error instanceof HTTPError && summaryQuery.error.response.status === 404
    ? 'ws.records.callReports.employees.notFound' : 'ws.records.callReports.employees.detailLoadFailed'

  const updateParams = useCallback((next: { start?: string; end?: string; trend?: TrendType }) => {
    const nextParams = new URLSearchParams(searchParams.toString())
    if (next.start) nextParams.set('start', next.start)
    if (next.end) nextParams.set('end', next.end)
    if (next.trend) nextParams.set('trend', next.trend)
    router.replace(`/workspace/records/call-reports/employees/${params.employeeId}?${nextParams.toString()}`)
  }, [params.employeeId, router, searchParams])

  return <div className="flex h-full flex-col overflow-auto"><div className="flex flex-col gap-5 p-6">
    <CallReportTabs active="employees" search={carriedSearch} />
    <DateToolbar start={start} end={end} asOf={summary?.as_of ?? null}
      loading={summaryQuery.isFetching || trendLoading || !dateRangeValid}
      onChange={updateParams} onRefresh={() => void queryClient.invalidateQueries({ queryKey: callAgentKeys.all })}
      exportAction={<CallReportExportButton
        params={{ kind: 'employee-detail', start, end, trend, employee_id: employeeId }}
        disabled={!validEmployee || !dateRangeValid || summaryQuery.isLoading || (summaryQuery.isError && !summary)}
      />} />
    {!validEmployee ? <DetailState messageKey="ws.records.callReports.employees.notFound" />
      : summaryQuery.isError && !summary ? <DetailState messageKey={errorMessageKey} onRetry={() => summaryQuery.refetch()} />
        : <>
          {summary ? <CallEmployeeDetailHeader employee={summary.employee} groupNames={summary.group_names} carriedSearch={carriedSearch} /> : <div className="h-14 animate-pulse rounded-lg bg-muted" />}
          {summary?.coverage.status !== 'unavailable' ? <CallEmployeeReportNotices coverage={summary?.coverage} dataQuality={summary?.data_quality} /> : null}
          {summary?.coverage.status === 'unavailable' ? <CallEmployeeHistoryUnavailable effectiveAt={summary.coverage.effective_at} /> : <>
            <CallEmployeeOverview metrics={summary?.metrics ?? []} distributions={summary?.distributions ?? []} loading={summaryQuery.isLoading} />
            <CallEmployeeTrend employeeId={employeeId} start={start} end={end} trend={trend}
              groups={groups.length ? groups : EMPLOYEE_GROUP_ORDER} enabled={dateRangeValid && Boolean(summary)}
              summaryLoading={summaryQuery.isLoading} onTrendChange={(value) => updateParams({ trend: value })}
              onLoadingChange={setTrendLoading} />
          </>}
        </>}
  </div></div>
}

function DetailState({ messageKey, onRetry }: { messageKey: string; onRetry?: () => void }) {
  const { locale } = useLocaleStore()
  return <div className="flex min-h-80 flex-col items-center justify-center gap-3 rounded-lg border border-border text-sm text-muted-foreground"><p>{t(messageKey, locale)}</p>{onRetry ? <button type="button" onClick={onRetry} className="h-9 rounded-md bg-primary px-4 text-primary-foreground">{t('ws.records.callReports.overall.retry', locale)}</button> : null}</div>
}
function todayIsoDate(): string { const date = new Date(); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}` }
function isValidRange(start: string, end: string): boolean { if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || start > end) return false; return (new Date(`${end}T00:00:00Z`).getTime() - new Date(`${start}T00:00:00Z`).getTime()) / 86_400_000 < 366 }
