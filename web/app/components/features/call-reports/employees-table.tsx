'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowDown, IconArrowUp, IconSearch } from '@tabler/icons-react'
import { EmployeeAvatar } from '@/app/components/features/session-reports/employee-avatar'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { useCallReportsEmployees } from '@/service/use-call-reports'
import { formatDuration } from '@/utils/format-duration'
import { t } from '@/utils/i18n'
import type {
  CallEmployeeOverviewRow,
  CallEmployeeSortField,
  CallOverviewMetrics,
  SortOrder,
} from '@/models/call-report'

type Props = {
  start: string
  end: string
  carriedSearch: string
  onListStateChange?: (state: {
    q: string
    sort: CallEmployeeSortField
    order: SortOrder
    loading: boolean
  }) => void
}

type MetricColumn = {
  key: Exclude<CallEmployeeSortField, 'name'>
  labelKey: string
  width: string
  duration?: boolean
}

const PER_PAGE_OPTIONS = [20, 50, 100]

const METRIC_COLUMNS: MetricColumn[] = [
  { key: 'total_calls', labelKey: 'ws.records.callReports.overview.totalCalls', width: 'w-[70px]' },
  { key: 'inbound_calls', labelKey: 'ws.records.callReports.overview.inboundCalls', width: 'w-[70px]' },
  { key: 'answered_inbound_calls', labelKey: 'ws.records.callReports.overview.answeredInboundCalls', width: 'w-[98px]' },
  { key: 'outbound_calls', labelKey: 'ws.records.callReports.overview.outboundCalls', width: 'w-[70px]' },
  { key: 'answered_outbound_calls', labelKey: 'ws.records.callReports.overview.answeredOutboundCalls', width: 'w-[98px]' },
  { key: 'avg_inbound_talk_seconds', labelKey: 'ws.records.callReports.overview.avgInboundTalkTime', width: 'w-[112px]', duration: true },
  { key: 'avg_outbound_talk_seconds', labelKey: 'ws.records.callReports.overview.avgOutboundTalkTime', width: 'w-[112px]', duration: true },
]

export function CallEmployeesTable({ start, end, carriedSearch, onListStateChange }: Props) {
  const { locale } = useLocaleStore()
  const router = useRouter()

  const [search, setSearch] = useState('')
  const [committedQ, setCommittedQ] = useState('')
  const [sort, setSort] = useState<CallEmployeeSortField>('total_calls')
  const [order, setOrder] = useState<SortOrder>('desc')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)

  const { data, isLoading, isFetching } = useCallReportsEmployees({
    start,
    end,
    q: committedQ || undefined,
    sort,
    order,
    page,
    per_page: perPage,
  })

  useEffect(() => {
    onListStateChange?.({
      q: committedQ,
      sort,
      order,
      loading: isFetching,
    })
  }, [committedQ, isFetching, onListStateChange, order, sort])

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 1
  const tail = carriedSearch ? `?${carriedSearch.replace(/^\?/, '')}` : ''

  const commitSearch = () => {
    setCommittedQ(search.trim())
    setPage(1)
  }

  const toggleSort = (nextSort: CallEmployeeSortField) => {
    if (nextSort === sort) {
      setOrder(order === 'desc' ? 'asc' : 'desc')
    } else {
      setSort(nextSort)
      setOrder(nextSort === 'name' ? 'asc' : 'desc')
    }
    setPage(1)
  }

  const goToDetail = (row: CallEmployeeOverviewRow) => {
    const selectedText = window.getSelection()?.toString()
    if (selectedText) return
    router.push(`/workspace/records/call-reports/employees/${row.employee.id}${tail}`)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex h-9 w-full max-w-80 items-center gap-2 rounded-lg border border-border bg-background px-3">
        <button
          type="button"
          onClick={commitSearch}
          title={t('ws.records.callReports.employees.searchPlaceholder', locale)}
          className="flex size-5 items-center justify-center text-muted-foreground hover:text-foreground"
        >
          <IconSearch size={16} />
        </button>
        <input
          type="search"
          value={search}
          onChange={(event) => {
            const value = event.target.value
            setSearch(value)
            if (!value) {
              setCommittedQ('')
              setPage(1)
            }
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') commitSearch()
          }}
          onBlur={commitSearch}
          placeholder={t('ws.records.callReports.employees.searchPlaceholder', locale)}
          className="min-w-0 flex-1 border-0 bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground"
        />
      </div>

      <div className="overflow-hidden rounded-lg border border-border">
        <div className="overflow-x-auto">
          <div className="flex h-12 min-w-[960px] items-center gap-2 bg-muted/60 px-4 text-xs font-semibold text-muted-foreground">
            <button
              type="button"
              onClick={() => toggleSort('name')}
              className="flex w-[180px] items-center gap-1 text-left transition-colors hover:text-foreground"
            >
              <span>{t('ws.records.callReports.employees.colEmployee', locale)}</span>
              {sort === 'name' && (
                order === 'desc' ? <IconArrowDown size={12} /> : <IconArrowUp size={12} />
              )}
            </button>
            <div className="w-[60px] text-center">
              {t('ws.records.callReports.employees.colStatus', locale)}
            </div>
            {METRIC_COLUMNS.map((column) => (
              <button
                type="button"
                key={column.key}
                onClick={() => toggleSort(column.key)}
                className={cn(column.width, 'flex items-center justify-center gap-1 transition-colors hover:text-foreground')}
              >
                <span className="min-w-0 whitespace-normal text-center leading-tight">
                  {t(column.labelKey, locale)}
                </span>
                {sort === column.key && (
                  order === 'desc' ? <IconArrowDown size={12} /> : <IconArrowUp size={12} />
                )}
              </button>
            ))}
          </div>

          {isLoading ? (
            <div className="min-w-[960px] px-4 py-16 text-center text-sm text-muted-foreground">
              {t('ws.records.sessionReports.common.loading', locale)}
            </div>
          ) : items.length === 0 ? (
            <div className="min-w-[960px] px-4 py-16 text-center text-sm text-muted-foreground">
              {committedQ
                ? t('ws.records.callReports.employees.emptyByQuery', locale)
                : t('ws.records.callReports.employees.empty', locale)}
            </div>
          ) : (
            items.map((row, index) => (
              <div
                key={row.employee.id}
                role="button"
                tabIndex={0}
                onClick={() => goToDetail(row)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') goToDetail(row)
                }}
                className={cn(
                  'flex h-[56px] min-w-[960px] cursor-pointer select-text items-center gap-2 border-b border-border px-4 text-left text-[13px] text-foreground transition-colors last:border-b-0 hover:bg-muted/35',
                  index % 2 === 1 ? 'bg-muted/20' : 'bg-background'
                )}
              >
                <div className="flex w-[180px] min-w-0 items-center gap-3">
                  <EmployeeAvatar employee={row.employee} />
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="truncate font-semibold text-foreground">
                      {row.employee.display_name ?? row.employee.name}
                    </span>
                    <span className="truncate text-xs text-muted-foreground">
                      {row.employee.username ?? row.employee.email ?? '—'}
                    </span>
                  </div>
                </div>
                <div className="w-[60px] text-center">
                  <span
                    className={cn(
                      'inline-flex items-center rounded-md px-2 py-0.5 text-xs',
                      row.employee.is_active
                        ? 'bg-success/10 text-success'
                        : 'bg-muted text-muted-foreground'
                    )}
                  >
                    {row.employee.is_active
                      ? t('ws.records.callReports.employees.statusActive', locale)
                      : t('ws.records.callReports.employees.statusInactive', locale)}
                  </span>
                </div>
                {METRIC_COLUMNS.map((column) => (
                  <div key={column.key} className={cn(column.width, 'text-center')}>
                    {renderMetric(row.metrics, column)}
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      </div>

      <div className="flex min-h-10 flex-wrap items-center justify-between gap-3 text-[13px]">
        <span className="text-muted-foreground">
          {t('ws.records.callReports.employees.total', locale, { total })}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            className="h-8 rounded-lg border border-border bg-background px-3 text-xs hover:bg-muted/50 disabled:opacity-50"
          >
            {t('ws.records.sessionReports.common.prev', locale)}
          </button>
          <span className="text-muted-foreground">
            {page} / {pages}
          </span>
          <button
            type="button"
            disabled={page >= pages}
            onClick={() => setPage((current) => Math.min(pages, current + 1))}
            className="h-8 rounded-lg border border-border bg-background px-3 text-xs hover:bg-muted/50 disabled:opacity-50"
          >
            {t('ws.records.sessionReports.common.next', locale)}
          </button>
        </div>
        <div className="flex items-center gap-2">
          {PER_PAGE_OPTIONS.map((option) => (
            <button
              type="button"
              key={option}
              onClick={() => {
                setPerPage(option)
                setPage(1)
              }}
              className={cn(
                'h-8 rounded-lg px-3 text-xs transition-colors',
                perPage === option
                  ? 'bg-foreground font-semibold text-background'
                  : 'border border-border bg-background text-muted-foreground hover:text-foreground'
              )}
            >
              {t('ws.records.sessionReports.common.perPage', locale, { n: option })}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function renderMetric(metrics: CallOverviewMetrics, column: MetricColumn): string {
  const value = metrics[column.key]
  if (column.duration) return formatDuration(value)
  return typeof value === 'number' ? value.toLocaleString() : '0'
}
