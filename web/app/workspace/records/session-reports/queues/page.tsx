'use client'

import { useCallback, useMemo, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { DateToolbar } from '@/app/components/features/session-reports/date-toolbar'
import { SessionReportExportButton } from '@/app/components/features/session-reports/export-button'
import { QueuesTable } from '@/app/components/features/session-reports/queues-table'
import { ReportTabs } from '@/app/components/features/session-reports/report-tabs'
import { useSessionReportsQueues } from '@/service/use-session-reports'
import type { QueueSortField, QueueType, SortOrder } from '@/models/session-report'

function todayIsoDate(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export default function SessionReportsQueuesPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [dateRangeValid, setDateRangeValid] = useState(true)
  const [exportState, setExportState] = useState<{
    q: string
    queue_type?: QueueType
    sort: QueueSortField
    order: SortOrder
    loading: boolean
  }>({
    q: '',
    sort: 'queued_session_count',
    order: 'desc',
    loading: false,
  })

  const today = todayIsoDate()
  const start = searchParams.get('start') || today
  const end = searchParams.get('end') || today

  const updateParams = useCallback(
    (next: { start?: string; end?: string }) => {
      const p = new URLSearchParams(searchParams.toString())
      if (next.start) p.set('start', next.start)
      if (next.end) p.set('end', next.end)
      router.replace(`/workspace/records/session-reports/queues?${p.toString()}`)
    },
    [router, searchParams]
  )

  const { data, refetch, isFetching } = useSessionReportsQueues({ start, end })
  const carriedSearch = useMemo(() => searchParams.toString(), [searchParams])

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        <ReportTabs active="queues" search={carriedSearch} />
        <DateToolbar
          start={start}
          end={end}
          asOf={data?.as_of ?? null}
          loading={isFetching}
          exportAction={
            <SessionReportExportButton
              variant="queue"
              params={{
                scope: 'list',
                start,
                end,
                q: exportState.q || undefined,
                queue_type: exportState.queue_type,
                sort: exportState.sort,
                order: exportState.order,
              }}
              disabled={!dateRangeValid || isFetching || exportState.loading}
            />
          }
          onChange={(r) => updateParams(r)}
          onRefresh={() => refetch()}
          onValidityChange={setDateRangeValid}
        />
        <QueuesTable
          start={start}
          end={end}
          carriedSearch={carriedSearch}
          onExportStateChange={setExportState}
        />
      </div>
    </div>
  )
}
