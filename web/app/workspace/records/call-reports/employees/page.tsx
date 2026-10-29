'use client'

import { useCallback, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useRouter, useSearchParams } from 'next/navigation'
import { DateToolbar } from '@/app/components/features/session-reports/date-toolbar'
import { CallEmployeesTable } from '@/app/components/features/call-reports/employees-table'
import { CallReportTabs } from '@/app/components/features/call-reports/report-tabs'
import { CallReportExportButton } from '@/app/components/features/call-reports/export-button'
import { callAgentKeys } from '@/service/use-call-agent-reports'
import type { CallEmployeeListExportState } from '@/models/call-report-export'

function todayIsoDate(): string {
  const date = new Date()
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export default function CallReportsEmployeesPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const queryClient = useQueryClient()
  const [dateRangeValid, setDateRangeValid] = useState(true)
  const [listLoading, setListLoading] = useState(false)
  const [asOf, setAsOf] = useState<string | null>(null)
  const [exportParams, setExportParams] = useState<CallEmployeeListExportState>({
    sort: 'handled_call_count',
    order: 'desc',
  })

  const today = todayIsoDate()
  const start = searchParams.get('start') || today
  const end = searchParams.get('end') || today

  const updateParams = useCallback(
    (next: { start?: string; end?: string }) => {
      const params = new URLSearchParams(searchParams.toString())
      if (next.start) params.set('start', next.start)
      if (next.end) params.set('end', next.end)
      router.replace(`/workspace/records/call-reports/employees?${params.toString()}`)
    },
    [router, searchParams]
  )

  const handleRefresh = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: callAgentKeys.all })
  }, [queryClient])

  const handleListState = useCallback((state: { loading: boolean; asOf: string | null; exportParams: CallEmployeeListExportState }) => {
    setListLoading(state.loading)
    setAsOf(state.asOf)
    setExportParams(state.exportParams)
  }, [])

  const carriedSearch = useMemo(() => searchParams.toString(), [searchParams])

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        <CallReportTabs active="employees" search={carriedSearch} />
        <DateToolbar
          start={start}
          end={end}
          asOf={asOf}
          loading={listLoading || !dateRangeValid}
          onChange={(range) => updateParams(range)}
          onRefresh={handleRefresh}
          onValidityChange={setDateRangeValid}
          exportAction={<CallReportExportButton
            params={{ kind: 'employee-list', start, end, ...exportParams }}
            disabled={!dateRangeValid || listLoading || !asOf}
          />}
        />
        <CallEmployeesTable
          start={start}
          end={end}
          carriedSearch={carriedSearch}
          enabled={dateRangeValid}
          onStateChange={handleListState}
        />
      </div>
    </div>
  )
}
