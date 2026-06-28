'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowDown, IconArrowUp, IconSearch } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { useSessionReportsQueues } from '@/service/use-session-reports'
import { t } from '@/utils/i18n'
import type { QueueReportMetrics, QueueSortField, QueueType, SortOrder } from '@/models/session-report'
import {
  formatQueueMetricValue,
  queueMetricFormat,
  queueMetricLabelKey,
  queueStatusLabelKey,
  queueTypeLabelKey,
} from './queue-types'

type ExportState = {
  q: string
  queue_type?: QueueType
  sort: QueueSortField
  order: SortOrder
  loading: boolean
}

type Props = {
  start: string
  end: string
  carriedSearch: string
  onExportStateChange?: (state: ExportState) => void
}

const PER_PAGE_OPTIONS = [20, 50, 100]

const COLS: { key: QueueSortField; labelKey: string; width: string; sortable: boolean }[] = [
  { key: 'queued_session_count', labelKey: queueMetricLabelKey.queued_session_count, width: 'w-[120px]', sortable: true },
  { key: 'assigned_queue_session_count', labelKey: queueMetricLabelKey.assigned_queue_session_count, width: 'w-[130px]', sortable: true },
  { key: 'unassigned_queue_session_count', labelKey: queueMetricLabelKey.unassigned_queue_session_count, width: 'w-[140px]', sortable: true },
  { key: 'queue_assign_rate', labelKey: queueMetricLabelKey.queue_assign_rate, width: 'w-[110px]', sortable: true },
  { key: 'avg_queue_duration_seconds', labelKey: queueMetricLabelKey.avg_queue_duration_seconds, width: 'w-[130px]', sortable: true },
  { key: 'max_queue_duration_seconds', labelKey: queueMetricLabelKey.max_queue_duration_seconds, width: 'w-[130px]', sortable: true },
  { key: 'final_session_count', labelKey: queueMetricLabelKey.final_session_count, width: 'w-[130px]', sortable: true },
]

export function QueuesTable({ start, end, carriedSearch, onExportStateChange }: Props) {
  const { locale } = useLocaleStore()
  const router = useRouter()
  const [search, setSearch] = useState('')
  const [committedQ, setCommittedQ] = useState('')
  const [queueType, setQueueType] = useState<QueueType | undefined>()
  const [sort, setSort] = useState<QueueSortField>('queued_session_count')
  const [order, setOrder] = useState<SortOrder>('desc')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)

  const { data, isLoading, isFetching } = useSessionReportsQueues({
    start,
    end,
    q: committedQ || undefined,
    queue_type: queueType,
    sort,
    order,
    page,
    per_page: perPage,
  })

  useEffect(() => {
    onExportStateChange?.({
      q: committedQ,
      queue_type: queueType,
      sort,
      order,
      loading: isFetching,
    })
  }, [committedQ, queueType, sort, order, isFetching, onExportStateChange])

  const items = data?.items ?? []
  const total = data?.total ?? 0
  const pages = data?.pages ?? 1
  const tail = carriedSearch ? `?${carriedSearch.replace(/^\?/, '')}` : ''

  const commitSearch = () => {
    setCommittedQ(search)
    setPage(1)
  }

  const toggleSort = (col: QueueSortField) => {
    if (col === sort) {
      setOrder(order === 'desc' ? 'asc' : 'desc')
    } else {
      setSort(col)
      setOrder(col === 'name' || col === 'queue_type' || col === 'status' ? 'asc' : 'desc')
    }
    setPage(1)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
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
            placeholder={t('ws.records.sessionReports.queues.searchPlaceholder', locale)}
            className="flex-1 border-0 bg-transparent text-[13px] text-foreground outline-none placeholder:text-[#999999]"
          />
        </div>
        <select
          value={queueType ?? 'all'}
          onChange={(e) => {
            setQueueType(e.target.value === 'all' ? undefined : e.target.value as QueueType)
            setPage(1)
          }}
          className="h-9 rounded-lg border border-border bg-background px-3 text-[13px] text-foreground outline-none"
        >
          <option value="all">{t('ws.records.sessionReports.queues.type.all', locale)}</option>
          <option value="employee_group">{t(queueTypeLabelKey.employee_group, locale)}</option>
          <option value="employee">{t(queueTypeLabelKey.employee, locale)}</option>
        </select>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <div className="min-w-max">
          <div className="flex h-12 items-center gap-4 bg-[#F8F8F8] px-6 text-xs font-semibold text-muted-foreground">
            <button
              type="button"
              onClick={() => toggleSort('name')}
              className="flex w-[260px] items-center gap-1 text-left transition-colors hover:text-foreground"
            >
              <span>{t('ws.records.sessionReports.queues.colQueue', locale)}</span>
              {sort === 'name' && (order === 'desc' ? <IconArrowDown size={12} /> : <IconArrowUp size={12} />)}
            </button>
            <button
              type="button"
              onClick={() => toggleSort('queue_type')}
              className="flex w-[100px] items-center justify-center gap-1 transition-colors hover:text-foreground"
            >
              <span>{t('ws.records.sessionReports.queues.colType', locale)}</span>
              {sort === 'queue_type' && (order === 'desc' ? <IconArrowDown size={12} /> : <IconArrowUp size={12} />)}
            </button>
            <button
              type="button"
              onClick={() => toggleSort('status')}
              className="flex w-[90px] items-center justify-center gap-1 transition-colors hover:text-foreground"
            >
              <span>{t('ws.records.sessionReports.queues.colStatus', locale)}</span>
              {sort === 'status' && (order === 'desc' ? <IconArrowDown size={12} /> : <IconArrowUp size={12} />)}
            </button>
            {COLS.map((col) => (
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
            <div className="w-[90px] text-center">
              {t('ws.records.sessionReports.queues.colAction', locale)}
            </div>
          </div>

          {isLoading ? (
            <div className="px-6 py-16 text-center text-sm text-muted-foreground">
              {t('ws.records.sessionReports.common.loading', locale)}
            </div>
          ) : items.length === 0 ? (
            <div className="px-6 py-16 text-center text-sm text-muted-foreground">
              {committedQ || queueType
                ? t('ws.records.sessionReports.queues.emptyByQuery', locale)
                : t('ws.records.sessionReports.queues.empty', locale)}
            </div>
          ) : (
            items.map((row, idx) => {
              const href = `/workspace/records/session-reports/queues/${row.queue.queue_type}/${row.queue.queue_id}${tail}`
              return (
                <div
                  role="button"
                  tabIndex={0}
                  key={`${row.queue.queue_type}-${row.queue.queue_id}`}
                  onClick={() => router.push(href)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') router.push(href)
                  }}
                  className={cn(
                    'flex h-[56px] cursor-pointer items-center gap-4 border-b border-[#F0F0F0] px-6 text-left text-[13px] transition-colors last:border-b-0 hover:bg-muted/30',
                    idx % 2 === 1 ? 'bg-[#FAFAFA]' : 'bg-background'
                  )}
                >
                  <div className="flex w-[260px] min-w-0 items-center gap-2">
                    <span className="truncate font-semibold text-foreground">{row.queue.name}</span>
                    {row.queue.queue_type === 'employee' && (
                      <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                        {t('ws.records.queue.personalQueue', locale)}
                      </span>
                    )}
                  </div>
                  <div className="w-[100px] text-center">
                    <QueueTypeTag type={row.queue.queue_type} />
                  </div>
                  <div className="w-[90px] text-center">
                    <QueueStatusTag status={row.queue.status} />
                  </div>
                  {COLS.map((col) => (
                    <div key={col.key} className={`${col.width} text-center`}>
                      {renderMetric(row.metrics, col.key)}
                    </div>
                  ))}
                  <div className="w-[90px] text-center text-foreground">
                    {t('ws.records.sessionReports.queues.viewDetails', locale)}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>

      <div className="flex h-10 items-center justify-between text-[13px]">
        <span className="text-muted-foreground">
          {t('ws.records.sessionReports.queues.total', locale, { total })}
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
          <span className="text-muted-foreground">{page} / {pages}</span>
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

function renderMetric(metrics: QueueReportMetrics, key: QueueSortField): string {
  if (key === 'name' || key === 'queue_type' || key === 'status') return ''
  return formatQueueMetricValue(metrics[key], queueMetricFormat[key])
}

function QueueTypeTag({ type }: { type: QueueType }) {
  const { locale } = useLocaleStore()
  return (
    <span className="inline-flex items-center rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground">
      {t(queueTypeLabelKey[type], locale)}
    </span>
  )
}

function QueueStatusTag({ status }: { status: keyof typeof queueStatusLabelKey }) {
  const { locale } = useLocaleStore()
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-md px-2 py-0.5 text-xs',
        status === 'active'
          ? 'bg-[#F0FDF4] text-[#16A34A]'
          : status === 'inactive'
            ? 'bg-[#F5F5F5] text-[#737373]'
            : 'bg-[#FEF2F2] text-[#DC2626]'
      )}
    >
      {t(queueStatusLabelKey[status], locale)}
    </span>
  )
}
