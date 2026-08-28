'use client'

import { IconLoader2, IconRefresh } from '@tabler/icons-react'

import type { Locale } from '@/context/locale-store'
import type { CallRecordListItem } from '@/models/call-center'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'

import type { CallRecordColumnDef } from './call-record-column-defs'

type Props = {
  locale: Locale
  items: CallRecordListItem[]
  columns: CallRecordColumnDef[]
  loading: boolean
  fetching: boolean
  error: boolean
  hasActiveFilters: boolean
  onRetry: () => void
  onSelect: (publicId: string) => void
  total: number
  pages: number
  page: number
  perPage: number
  onPageChange: (page: number) => void
  onPerPageChange: (perPage: number) => void
}

const PER_PAGE_OPTIONS = [20, 50, 100]

function visiblePageNumbers(page: number, pages: number): number[] {
  const count = Math.min(pages, 7)
  return Array.from({ length: count }, (_, index) => {
    if (pages <= 7 || page <= 4) return index + 1
    if (page >= pages - 3) return pages - 6 + index
    return page - 3 + index
  })
}

export function CallRecordTable(props: Props) {
  const { locale, items, columns } = props
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col px-6 pt-4">
      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-border bg-background">
        {props.fetching && !props.loading && <div className="absolute right-3 top-3 z-20"><IconLoader2 size={16} className="animate-spin text-muted-foreground" /></div>}
        <div className="min-h-0 flex-1 overflow-auto">
          {props.loading ? (
            <div className="flex h-full min-h-[240px] items-center justify-center"><IconLoader2 size={24} className="animate-spin text-muted-foreground" /></div>
          ) : props.error ? (
            <div className="flex h-full min-h-[240px] flex-col items-center justify-center gap-3 px-4 text-center">
              <p className="text-sm text-muted-foreground">{t('ws.records.calls.loadFailed', locale)}</p>
              <button type="button" onClick={props.onRetry} className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm hover:bg-muted"><IconRefresh size={15} />{t('ws.records.calls.retry', locale)}</button>
            </div>
          ) : items.length === 0 ? (
            <div className="flex h-full min-h-[240px] items-center justify-center px-4"><p className="text-sm text-muted-foreground">{t(props.hasActiveFilters ? 'ws.records.calls.emptyFiltered' : 'ws.records.calls.empty', locale)}</p></div>
          ) : (
            <table className="w-max min-w-full table-auto border-separate border-spacing-0">
              <thead>
                <tr>{columns.map((column, index) => (
                  <th key={column.key} className={cn('sticky top-0 z-10 border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground', column.thClass, index === 0 && 'pl-4')}>
                    {t(column.labelKey, locale)}
                  </th>
                ))}</tr>
              </thead>
              <tbody>{items.map((record) => (
                <tr key={record.public_id} onClick={() => { if (!window.getSelection()?.toString()) props.onSelect(record.public_id) }} className="cursor-pointer transition-colors hover:bg-accent/30">
                  {columns.map((column, index) => (
                    <td key={column.key} className={cn('border-b border-border px-3 py-3 text-sm', column.tdClass, index === 0 && 'pl-4')}>
                      {column.render(record, locale)}
                    </td>
                  ))}
                </tr>
              ))}</tbody>
            </table>
          )}
        </div>
      </div>
      {props.total > 0 && (
        <div className="flex shrink-0 items-center justify-between py-3">
          <span className="text-xs text-muted-foreground">{t('ws.records.calls.paginationTotal', locale, { count: props.total })}</span>
          <div className="flex items-center gap-2">
            <select value={props.perPage} onChange={(event) => props.onPerPageChange(Number(event.target.value))} className="h-8 rounded-md border border-border bg-background px-2 text-xs outline-none">
              {PER_PAGE_OPTIONS.map((value) => <option key={value} value={value}>{value} / page</option>)}
            </select>
            <div className="flex gap-1">{visiblePageNumbers(props.page, props.pages).map((pageNumber) => (
              <button key={pageNumber} type="button" onClick={() => props.onPageChange(pageNumber)} className={cn('flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-xs transition-colors', props.page === pageNumber ? 'bg-primary text-primary-foreground' : 'border border-border text-foreground hover:bg-accent')}>
                {pageNumber}
              </button>
            ))}</div>
          </div>
        </div>
      )}
    </div>
  )
}
