'use client'

import { IconArrowDown, IconArrowUp, IconChevronRight } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import type {
  CallQueueOverviewRow,
  CallQueueSortField,
} from '@/models/call-queue-report'
import type { SortOrder } from '@/models/call-report'
import { formatDuration } from '@/utils/format-duration'
import { t } from '@/utils/i18n'

type Props = {
  items: CallQueueOverviewRow[]
  loading: boolean
  query: string
  sort: CallQueueSortField
  order: SortOrder
  onSort: (sort: CallQueueSortField) => void
  onOpen: (row: CallQueueOverviewRow) => void
}

type Column = {
  key: CallQueueSortField
  labelKey: string
  width: string
  format?: 'duration' | 'percent'
}

const COLUMNS: Column[] = [
  { key: 'queue_call_count', labelKey: 'ws.records.callReports.queues.metric.queue_call_count', width: 'w-[90px]' },
  { key: 'queue_entry_count', labelKey: 'ws.records.callReports.queues.metric.queue_entry_count', width: 'w-[90px]' },
  { key: 'queue_answered_count', labelKey: 'ws.records.callReports.queues.metric.queue_answered_count', width: 'w-[90px]' },
  { key: 'queue_answer_rate', labelKey: 'ws.records.callReports.queues.metric.queue_answer_rate', width: 'w-[90px]', format: 'percent' },
  { key: 'queue_abandoned_count', labelKey: 'ws.records.callReports.queues.metric.queue_abandoned_count', width: 'w-[90px]' },
  { key: 'queue_abandon_rate', labelKey: 'ws.records.callReports.queues.metric.queue_abandon_rate', width: 'w-[90px]', format: 'percent' },
  { key: 'avg_answer_wait_seconds', labelKey: 'ws.records.callReports.queues.metric.avg_answer_wait_seconds', width: 'w-[110px]', format: 'duration' },
  { key: 'queue_service_level_20s', labelKey: 'ws.records.callReports.queues.metric.queue_service_level_20s', width: 'w-[100px]', format: 'percent' },
]

export function CallQueueTable({ items, loading, query, sort, order, onSort, onOpen }: Props) {
  const { locale } = useLocaleStore()
  const sortHeader = (column: Column) => (
    <button key={column.key} type="button" onClick={() => onSort(column.key)}
      className={cn(column.width, 'flex items-center justify-center gap-1 transition-colors hover:text-foreground')}>
      <span className="whitespace-normal text-center leading-tight">{t(column.labelKey, locale)}</span>
      {sort === column.key ? order === 'desc' ? <IconArrowDown size={12} /> : <IconArrowUp size={12} /> : null}
    </button>
  )

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="overflow-x-auto">
        <div className="flex h-12 min-w-[1260px] items-center gap-2 bg-muted/60 px-4 text-xs font-semibold text-muted-foreground">
          <button type="button" onClick={() => onSort('name')}
            className="flex w-[190px] items-center gap-1 text-left hover:text-foreground">
            {t('ws.records.callReports.queues.colQueue', locale)}
            {sort === 'name' ? order === 'desc' ? <IconArrowDown size={12} /> : <IconArrowUp size={12} /> : null}
          </button>
          <button type="button" onClick={() => onSort('queue_type')}
            className="flex w-[88px] items-center justify-center gap-1 hover:text-foreground">
            {t('ws.records.callReports.queues.colType', locale)}
          </button>
          <button type="button" onClick={() => onSort('status')}
            className="flex w-[72px] items-center justify-center gap-1 hover:text-foreground">
            {t('ws.records.callReports.queues.colStatus', locale)}
          </button>
          {COLUMNS.map(sortHeader)}
          <div className="w-[64px] text-center">{t('ws.records.callReports.queues.colAction', locale)}</div>
        </div>
        {loading ? (
          <TableState text={t('ws.records.sessionReports.common.loading', locale)} />
        ) : items.length === 0 ? (
          <TableState text={t(query ? 'ws.records.callReports.queues.emptyByQuery' : 'ws.records.callReports.queues.empty', locale)} />
        ) : items.map((row, index) => (
          <div key={`${row.queue.queue_type}-${row.queue.queue_id}`} role="button" tabIndex={0}
            onClick={() => openUnlessSelecting(row, onOpen)}
            onKeyDown={(event) => { if (event.key === 'Enter') onOpen(row) }}
            className={cn(
              'flex h-14 min-w-[1260px] cursor-pointer select-text items-center gap-2 border-b border-border px-4 text-[13px] text-foreground last:border-b-0 hover:bg-muted/35',
              index % 2 === 1 ? 'bg-muted/20' : 'bg-background',
            )}>
            <div className="w-[190px] truncate font-semibold">{row.queue.name}</div>
            <div className="w-[88px] text-center">{t(`ws.records.callReports.queues.type.${row.queue.queue_type}`, locale)}</div>
            <div className="w-[72px] text-center">
              <span className={cn('rounded-md px-2 py-0.5 text-xs', row.queue.status === 'active'
                ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground')}>
                {t(`ws.records.callReports.queues.status.${row.queue.status}`, locale)}
              </span>
            </div>
            {COLUMNS.map((column) => (
              <div key={column.key} className={cn(column.width, 'text-center font-mono')}>
                {formatValue(row, column, locale)}
              </div>
            ))}
            <div className="flex w-[64px] justify-center">
              <button type="button" title={t('ws.records.callReports.queues.viewDetail', locale)}
                onClick={(event) => { event.stopPropagation(); onOpen(row) }}
                className="flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
                <IconChevronRight size={17} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function TableState({ text }: { text: string }) {
  return <div className="min-w-[1260px] px-4 py-16 text-center text-sm text-muted-foreground">{text}</div>
}

function formatValue(row: CallQueueOverviewRow, column: Column, locale: string): string {
  const value = row.metrics[column.key as keyof typeof row.metrics]
  if (value === null || value === undefined) return '—'
  if (column.format === 'duration') return formatDuration(value)
  if (column.format === 'percent') return new Intl.NumberFormat(locale, {
    style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1,
  }).format(value)
  return new Intl.NumberFormat(locale).format(value)
}

function openUnlessSelecting(row: CallQueueOverviewRow, onOpen: Props['onOpen']) {
  if (!window.getSelection()?.toString()) onOpen(row)
}
