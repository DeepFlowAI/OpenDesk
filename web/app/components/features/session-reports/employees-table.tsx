'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowDown, IconArrowUp, IconSearch } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { useSessionReportsEmployees } from '@/service/use-session-reports'
import { formatDuration } from '@/utils/format-duration'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import type { EmployeeSortField, SortOrder } from '@/models/session-report'
import { EmployeeAvatar } from './employee-avatar'

type Props = {
  start: string
  end: string
  /** Forwarded to the detail page navigation so URL params (start/end/trend) are preserved */
  carriedSearch: string
  refreshToken?: number
  onExportStateChange?: (state: {
    q: string
    sort: EmployeeSortField
    order: SortOrder
    loading: boolean
    asOf: string | null
  }) => void
}

const PER_PAGE_OPTIONS = [20, 50, 100]

const COLS: { key: EmployeeSortField; labelKey: string; width: string; sortable: boolean }[] = [
  { key: 'name', labelKey: 'ws.records.sessionReports.overview.title', width: 'w-[240px]', sortable: false },
  // ^ first col rendered specially (employee identity); the labelKey above isn't used here
  { key: 'session_count', labelKey: 'ws.records.sessionReports.overview.sessionCount', width: 'w-[100px]', sortable: true },
  { key: 'message_count', labelKey: 'ws.records.sessionReports.overview.messageCount', width: 'w-[100px]', sortable: true },
  { key: 'user_message_count', labelKey: 'ws.records.sessionReports.overview.userMessageCount', width: 'w-[110px]', sortable: true },
  { key: 'agent_message_count', labelKey: 'ws.records.sessionReports.overview.agentMessageCount', width: 'w-[110px]', sortable: true },
  { key: 'avg_duration_seconds', labelKey: 'ws.records.sessionReports.overview.avgDuration', width: 'w-[130px]', sortable: true },
  { key: 'reception_segment_count', labelKey: 'ws.records.sessionReports.overview.receptionSegmentCount', width: 'w-[110px]', sortable: true },
  { key: 'reception_transfer_in_count', labelKey: 'ws.records.sessionReports.overview.receptionTransferInCount', width: 'w-[110px]', sortable: true },
  { key: 'reception_transfer_out_count', labelKey: 'ws.records.sessionReports.overview.receptionTransferOutCount', width: 'w-[110px]', sortable: true },
]

export function EmployeesTable({ start, end, carriedSearch, refreshToken = 0, onExportStateChange }: Props) {
  const { locale } = useLocaleStore()
  const router = useRouter()

  const [search, setSearch] = useState('')
  const [committedQ, setCommittedQ] = useState('')
  const [sort, setSort] = useState<EmployeeSortField>('session_count')
  const [order, setOrder] = useState<SortOrder>('desc')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)

  const { data, isLoading, isFetching, refetch } = useSessionReportsEmployees({
    start,
    end,
    q: committedQ || undefined,
    sort,
    order,
    page,
    per_page: perPage,
  })

  useEffect(() => {
    onExportStateChange?.({
      q: committedQ,
      sort,
      order,
      loading: isFetching,
      asOf: data?.as_of ?? null,
    })
  }, [committedQ, sort, order, isFetching, data?.as_of, onExportStateChange])

  useEffect(() => {
    if (refreshToken > 0) {
      refetch()
    }
  }, [refreshToken, refetch])

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 1

  const tail = carriedSearch ? `?${carriedSearch.replace(/^\?/, '')}` : ''

  const commitSearch = () => {
    setCommittedQ(search)
    setPage(1)
  }
  const toggleSort = (col: EmployeeSortField) => {
    if (col === sort) {
      setOrder(order === 'desc' ? 'asc' : 'desc')
    } else {
      setSort(col)
      setOrder(col === 'name' ? 'asc' : 'desc')
    }
    setPage(1)
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Search toolbar */}
      <div>
        <div className="flex h-9 w-80 items-center gap-2 rounded-lg border border-border bg-background px-3">
          <IconSearch size={16} className="text-[#999999]" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitSearch()
            }}
            onBlur={commitSearch}
            placeholder={t('ws.records.sessionReports.employees.searchPlaceholder', locale)}
            className="flex-1 border-0 bg-transparent text-[13px] text-foreground outline-none placeholder:text-[#999999]"
          />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <div className="min-w-max">
          {/* Header */}
          <div className="flex h-12 items-center gap-4 bg-[#F8F8F8] px-6 text-xs font-semibold text-muted-foreground">
            <div className="w-[240px]">
              {t('ws.records.sessionReports.employees.colEmployee', locale)}
            </div>
            <div className="w-[80px] text-center">
              {t('ws.records.sessionReports.employees.colStatus', locale)}
            </div>
            {COLS.filter((c) => c.sortable).map((col) => (
              <button
                type="button"
                key={col.key}
                onClick={() => toggleSort(col.key)}
                className={cn(col.width, 'flex items-center justify-center gap-1 transition-colors hover:text-foreground')}
              >
                <span>{t(col.labelKey, locale)}</span>
                {sort === col.key && (order === 'desc' ? <IconArrowDown size={12} /> : <IconArrowUp size={12} />)}
              </button>
            ))}
          </div>

          {/* Rows */}
          {isLoading ? (
            <div className="px-6 py-16 text-center text-sm text-muted-foreground">
              {t('ws.records.sessionReports.common.loading', locale)}
            </div>
          ) : items.length === 0 ? (
            <div className="px-6 py-16 text-center text-sm text-muted-foreground">
              {committedQ
                ? t('ws.records.sessionReports.employees.emptyByQuery', locale)
                : t('ws.records.sessionReports.employees.empty', locale)}
            </div>
          ) : (
            items.map((row, idx) => {
              const e = row.employee
              const m = row.metrics
              const href = `/workspace/records/session-reports/employees/${e.id}${tail}`
              return (
                <div
                  role="button"
                  tabIndex={0}
                  key={e.id}
                  onClick={() => {
                    if (window.getSelection()?.toString()) return
                    router.push(href)
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      router.push(href)
                    }
                  }}
                  className={cn(
                    'flex h-[56px] cursor-pointer select-text items-center gap-4 border-b border-[#F0F0F0] px-6 text-left text-[13px] transition-colors last:border-b-0 hover:bg-muted/30',
                    idx % 2 === 1 ? 'bg-[#FAFAFA]' : 'bg-background'
                  )}
                >
                  <div className="flex w-[240px] items-center gap-3">
                    <EmployeeAvatar employee={e} />
                    <div className="flex flex-col gap-0.5">
                      <span className="font-semibold text-foreground">
                        {e.display_name ?? e.name}
                      </span>
                      {e.email && (
                        <span className="text-xs text-muted-foreground">{e.email}</span>
                      )}
                    </div>
                  </div>
                  <div className="w-[80px] text-center">
                    <span
                      className={cn(
                        'inline-flex items-center rounded-md px-2 py-0.5 text-xs',
                        e.is_active ? 'bg-[#F0FDF4] text-[#16A34A]' : 'bg-[#F5F5F5] text-[#737373]'
                      )}
                    >
                      {e.is_active
                        ? t('ws.records.sessionReports.employees.statusActive', locale)
                        : t('ws.records.sessionReports.employees.statusInactive', locale)}
                    </span>
                  </div>
                  <div className="w-[100px] text-center">{m.session_count.toLocaleString()}</div>
                  <div className="w-[100px] text-center">{m.message_count.toLocaleString()}</div>
                  <div className="w-[110px] text-center">{m.user_message_count.toLocaleString()}</div>
                  <div className="w-[110px] text-center">{m.agent_message_count.toLocaleString()}</div>
                  <div className="w-[130px] text-center">{formatDuration(m.avg_duration_seconds)}</div>
                  <div className="w-[110px] text-center">{(m.reception_segment_count ?? 0).toLocaleString()}</div>
                  <div className="w-[110px] text-center">{(m.reception_transfer_in_count ?? 0).toLocaleString()}</div>
                  <div className="w-[110px] text-center">{(m.reception_transfer_out_count ?? 0).toLocaleString()}</div>
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* Pagination */}
      <div className="flex h-10 items-center justify-between text-[13px]">
        <span className="text-muted-foreground">
          {t('ws.records.sessionReports.employees.total', locale, { total })}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
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
            onClick={() => setPage((p) => Math.min(pages, p + 1))}
            className="h-8 rounded-lg border border-border bg-background px-3 text-xs hover:bg-muted/50 disabled:opacity-50"
          >
            {t('ws.records.sessionReports.common.next', locale)}
          </button>
        </div>
        <div className="flex items-center gap-2">
          {PER_PAGE_OPTIONS.map((n) => (
            <button
              type="button"
              key={n}
              onClick={() => {
                setPerPage(n)
                setPage(1)
              }}
              className={cn(
                'h-8 rounded-lg px-3 text-xs transition-colors',
                perPage === n
                  ? 'bg-foreground font-semibold text-background'
                  : 'border border-border bg-background text-muted-foreground hover:text-foreground'
              )}
            >
              {t('ws.records.sessionReports.common.perPage', locale, { n })}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
