'use client'

import { useCallback, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { IconSearch } from '@tabler/icons-react'
import { useRouter, useSearchParams } from 'next/navigation'
import { CallQueueTable } from '@/app/components/features/call-reports/queues/queue-table'
import { CallHistoryUnavailable, CallReportNotices } from '@/app/components/features/call-reports/overall/report-notices'
import { CallReportTabs } from '@/app/components/features/call-reports/report-tabs'
import { CallReportExportButton } from '@/app/components/features/call-reports/export-button'
import { DateToolbar } from '@/app/components/features/session-reports/date-toolbar'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import type { SortOrder } from '@/models/call-report'
import type { CallQueueSortField, CallQueueTypeFilter } from '@/models/call-queue-report'
import { callQueueKeys, useCallQueueList } from '@/service/use-call-queue-reports'
import { t } from '@/utils/i18n'

const PER_PAGE_OPTIONS = [20, 50, 100]

export default function CallReportsQueuesPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const queryClient = useQueryClient()
  const { locale } = useLocaleStore()
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [queueType, setQueueType] = useState<CallQueueTypeFilter>('employee_group')
  const [sort, setSort] = useState<CallQueueSortField>('queue_entry_count')
  const [order, setOrder] = useState<SortOrder>('desc')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)

  const today = todayIsoDate()
  const start = searchParams.get('start') || today
  const end = searchParams.get('end') || today
  const dateRangeValid = isValidRange(start, end)
  const list = useCallQueueList({ start, end, q: query || undefined, queueType, sort, order, page, perPage, enabled: dateRangeValid })
  const data = list.data
  const carriedSearch = useMemo(() => searchParams.toString(), [searchParams])

  const updateDates = useCallback((next: { start?: string; end?: string }) => {
    const params = new URLSearchParams(searchParams.toString())
    if (next.start) params.set('start', next.start)
    if (next.end) params.set('end', next.end)
    router.replace(`/workspace/records/call-reports/queues?${params.toString()}`)
  }, [router, searchParams])

  const commitSearch = () => { setQuery(search.trim()); setPage(1) }
  const toggleSort = (next: CallQueueSortField) => {
    if (next === sort) setOrder(order === 'desc' ? 'asc' : 'desc')
    else { setSort(next); setOrder(next === 'name' ? 'asc' : 'desc') }
    setPage(1)
  }
  const quality = data?.data_quality ? { ...data.data_quality, satisfaction_pending: 0 } : undefined

  return (
    <div className="flex h-full flex-col overflow-auto">
      <div className="flex flex-col gap-5 p-6">
        <CallReportTabs active="queues" search={carriedSearch} />
        <DateToolbar start={start} end={end} asOf={data?.as_of ?? null}
          loading={list.isFetching || !dateRangeValid} onChange={updateDates}
          onRefresh={() => void queryClient.invalidateQueries({ queryKey: callQueueKeys.all })}
          exportAction={<CallReportExportButton
            params={{ kind: 'queue-list', start, end, q: query || undefined, queue_type: queueType, sort, order }}
            disabled={!dateRangeValid || list.isLoading || (list.isError && !data)}
          />} />
        {list.isError && !data ? <LoadError onRetry={() => list.refetch()} /> : (
          <>
            {data?.coverage.status !== 'unavailable' ? <CallReportNotices coverage={data?.coverage} dataQuality={quality} /> : null}
            {data?.coverage.status === 'unavailable' ? <CallHistoryUnavailable effectiveAt={data.coverage.effective_at} /> : (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex h-9 w-full max-w-80 items-center gap-2 rounded-lg border border-border bg-background px-3">
                    <button type="button" onClick={commitSearch} className="text-muted-foreground hover:text-foreground"><IconSearch size={16} /></button>
                    <input type="search" value={search} onChange={(event) => { setSearch(event.target.value); if (!event.target.value) { setQuery(''); setPage(1) } }}
                      onKeyDown={(event) => { if (event.key === 'Enter') commitSearch() }} onBlur={commitSearch}
                      placeholder={t('ws.records.callReports.queues.searchPlaceholder', locale)}
                      className="min-w-0 flex-1 border-0 bg-transparent text-[13px] outline-none placeholder:text-muted-foreground" />
                  </div>
                  <select value={queueType} onChange={(event) => { setQueueType(event.target.value as CallQueueTypeFilter); setPage(1) }}
                    className="h-9 rounded-lg border border-border bg-background px-3 text-[13px] text-foreground outline-none">
                    {(['employee_group', 'employee', 'all'] as const).map((type) => (
                      <option key={type} value={type}>{t(`ws.records.callReports.queues.filter.${type}`, locale)}</option>
                    ))}
                  </select>
                </div>
                <CallQueueTable items={data?.items ?? []} loading={list.isLoading} query={query} sort={sort} order={order}
                  onSort={toggleSort} onOpen={(row) => router.push(`/workspace/records/call-reports/queues/${row.queue.queue_type}/${row.queue.queue_id}${carriedSearch ? `?${carriedSearch}` : ''}`)} />
                <Pagination page={data?.page ?? page} pages={data?.pages ?? 1} total={data?.total ?? 0}
                  perPage={perPage} onPage={setPage} onPerPage={(value) => { setPerPage(value); setPage(1) }} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function Pagination(props: { page: number; pages: number; total: number; perPage: number; onPage: (page: number) => void; onPerPage: (value: number) => void }) {
  const { locale } = useLocaleStore()
  return (
    <div className="flex min-h-10 flex-wrap items-center justify-between gap-3 text-[13px]">
      <span className="text-muted-foreground">{t('ws.records.callReports.queues.total', locale, { total: props.total })}</span>
      <div className="flex items-center gap-2">
        <button type="button" disabled={props.page <= 1} onClick={() => props.onPage(props.page - 1)} className="h-8 rounded-lg border border-border px-3 text-xs disabled:opacity-50">{t('ws.records.sessionReports.common.prev', locale)}</button>
        <span className="text-muted-foreground">{props.page} / {props.pages}</span>
        <button type="button" disabled={props.page >= props.pages} onClick={() => props.onPage(props.page + 1)} className="h-8 rounded-lg border border-border px-3 text-xs disabled:opacity-50">{t('ws.records.sessionReports.common.next', locale)}</button>
      </div>
      <div className="flex gap-2">{PER_PAGE_OPTIONS.map((option) => (
        <button type="button" key={option} onClick={() => props.onPerPage(option)} className={cn('h-8 rounded-lg px-3 text-xs', props.perPage === option ? 'bg-foreground font-semibold text-background' : 'border border-border text-muted-foreground')}>{t('ws.records.sessionReports.common.perPage', locale, { n: option })}</button>
      ))}</div>
    </div>
  )
}

function LoadError({ onRetry }: { onRetry: () => void }) {
  const { locale } = useLocaleStore()
  return <div className="flex min-h-80 flex-col items-center justify-center gap-3 rounded-lg border border-border text-sm text-muted-foreground">
    <p>{t('ws.records.callReports.queues.loadFailed', locale)}</p>
    <button type="button" onClick={onRetry} className="h-9 rounded-md bg-primary px-4 text-primary-foreground">{t('ws.records.callReports.overall.retry', locale)}</button>
  </div>
}

function todayIsoDate(): string {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function isValidRange(start: string, end: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || start > end) return false
  return (new Date(`${end}T00:00:00Z`).getTime() - new Date(`${start}T00:00:00Z`).getTime()) / 86_400_000 < 366
}
