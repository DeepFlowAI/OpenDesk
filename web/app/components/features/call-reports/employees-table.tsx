'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { IconArrowDown, IconArrowUp, IconSearch } from '@tabler/icons-react'
import { useRouter } from 'next/navigation'
import { EmployeeAvatar } from '@/app/components/features/session-reports/employee-avatar'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import type { CallAgentOverviewMetrics, CallAgentOverviewRow, CallAgentSortField } from '@/models/call-agent-report'
import type { CallEmployeeListExportState } from '@/models/call-report-export'
import type { SortOrder } from '@/models/call-report'
import type { CallMetricFormat } from '@/models/call-report-overall'
import { useCallAgentList } from '@/service/use-call-agent-reports'
import { useEmployeeGroups } from '@/service/use-employee-groups'
import { t } from '@/utils/i18n'
import { getDataScope } from '@/utils/permissions'
import { CallEmployeeHistoryUnavailable, CallEmployeeReportNotices } from './employees/employee-report-notices'
import { callMetricLabel, formatCallMetric } from './overall/metric-format'

const PER_PAGE_OPTIONS = [20, 50, 100]
const COLUMNS: Array<{ key: CallAgentSortField; format: CallMetricFormat }> = [
  { key: 'participated_call_count', format: 'integer' }, { key: 'handled_call_count', format: 'integer' },
  { key: 'reception_segment_count', format: 'integer' }, { key: 'inbound_handled_call_count', format: 'integer' },
  { key: 'outbound_attempt_count', format: 'integer' }, { key: 'outbound_customer_answered_count', format: 'integer' },
  { key: 'offer_accept_rate', format: 'percent' }, { key: 'avg_talk_seconds', format: 'duration_seconds' },
  { key: 'avg_handle_seconds', format: 'duration_seconds' }, { key: 'transfer_completed_count', format: 'integer' },
]

export function CallEmployeesTable({ start, end, carriedSearch, enabled, onStateChange }: {
  start: string; end: string; carriedSearch: string; enabled: boolean
  onStateChange?: (state: { loading: boolean; asOf: string | null; exportParams: CallEmployeeListExportState }) => void
}) {
  const { locale } = useLocaleStore()
  const user = useAuthStore((state) => state.user)
  const router = useRouter()
  const scope = getDataScope(user, 'call_record')
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [groupId, setGroupId] = useState(0)
  const [status, setStatus] = useState('')
  const [sort, setSort] = useState<CallAgentSortField>('handled_call_count')
  const [order, setOrder] = useState<SortOrder>('desc')
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const groupsQuery = useEmployeeGroups({ per_page: 200, member_id: scope === 'group' ? user?.id : undefined })
  const query = useCallAgentList({ start, end, q, groupId: groupId || undefined, status: status || undefined,
    sort, order, page, perPage, enabled })
  const data = query.data
  const hasFilters = Boolean(q || groupId || status)

  useEffect(() => {
    onStateChange?.({
      loading: query.isFetching,
      asOf: data?.as_of ?? null,
      exportParams: { q: q || undefined, group_id: groupId || undefined, status: status || undefined, sort, order },
    })
  }, [data?.as_of, groupId, onStateChange, order, q, query.isFetching, sort, status])
  useEffect(() => { if (data && page > data.pages) setPage(Math.max(1, data.pages)) }, [data, page])

  const commitSearch = () => { setQ(search.trim()); setPage(1) }
  const toggleSort = (next: CallAgentSortField) => {
    if (sort === next) setOrder((value) => value === 'desc' ? 'asc' : 'desc')
    else { setSort(next); setOrder(next === 'name' || next === 'status' ? 'asc' : 'desc') }
    setPage(1)
  }
  const goToDetail = (row: CallAgentOverviewRow) => {
    if (window.getSelection()?.toString()) return
    const tail = carriedSearch ? `?${carriedSearch.replace(/^\?/, '')}` : ''
    router.push(`/workspace/records/call-reports/employees/${row.employee.id}${tail}`)
  }

  return <div className="flex flex-col gap-4">
    {data?.coverage.status !== 'unavailable' ? <CallEmployeeReportNotices coverage={data?.coverage} dataQuality={data?.data_quality} /> : null}
    {scope !== 'self' ? <div className="flex flex-wrap gap-2">
      <div className="flex h-9 w-full max-w-72 items-center gap-2 rounded-lg border border-border bg-background px-3">
        <button type="button" onClick={commitSearch} title={t('ws.records.callReports.employees.searchPlaceholder', locale)} className="text-muted-foreground hover:text-foreground"><IconSearch size={16} /></button>
        <input type="search" value={search} onChange={(event) => { setSearch(event.target.value); if (!event.target.value) { setQ(''); setPage(1) } }}
          onKeyDown={(event) => { if (event.key === 'Enter') commitSearch() }} onBlur={commitSearch}
          placeholder={t('ws.records.callReports.employees.searchPlaceholder', locale)} className="min-w-0 flex-1 bg-transparent text-[13px] outline-none" />
      </div>
      <FilterSelect value={String(groupId)} onChange={(value) => { setGroupId(Number(value)); setPage(1) }}
        label={t('ws.records.callReports.employees.groupFilter', locale)} options={[
          ['0', t('ws.records.callReports.employees.groupAll', locale)],
          ...(groupsQuery.data?.items ?? []).map((group) => [String(group.id), group.name] as [string, string]),
        ]} />
      <FilterSelect value={status} onChange={(value) => { setStatus(value); setPage(1) }}
        label={t('ws.records.callReports.employees.statusFilter', locale)} options={[
          ['', t('ws.records.callReports.employees.statusAll', locale)],
          ['active', t('ws.records.callReports.employees.statusActive', locale)],
          ['inactive', t('ws.records.callReports.employees.statusInactive', locale)],
          ['deleted', t('ws.records.callReports.employees.statusDeleted', locale)],
        ]} />
    </div> : null}
    {data?.coverage.status === 'unavailable' ? <CallEmployeeHistoryUnavailable effectiveAt={data.coverage.effective_at} />
      : query.isError && !data ? <TableState message={t('ws.records.callReports.employees.loadFailed', locale)} onRetry={() => query.refetch()} />
        : <div className="overflow-x-auto rounded-lg border border-border"><table className="min-w-[1760px] border-collapse text-[13px]">
          <thead><tr className="h-12 bg-muted/60 text-xs font-semibold text-muted-foreground">
            <SortHead field="name" sort={sort} order={order} onSort={toggleSort} className="sticky left-0 z-20 min-w-56 bg-muted px-4 text-left">{t('ws.records.callReports.employees.colEmployee', locale)}</SortHead>
            <SortHead field="status" sort={sort} order={order} onSort={toggleSort}>{t('ws.records.callReports.employees.colStatus', locale)}</SortHead>
            {COLUMNS.map((column) => <SortHead key={column.key} field={column.key} sort={sort} order={order} onSort={toggleSort}>{callMetricLabel(column.key, locale)}</SortHead>)}
            <th className="sticky right-0 z-20 min-w-28 bg-muted px-4 text-right">{t('ws.records.callReports.employees.colAction', locale)}</th>
          </tr></thead>
          <tbody>{query.isLoading ? <tr><td colSpan={13}><TableState message={t('ws.records.sessionReports.common.loading', locale)} /></td></tr>
            : !data?.items.length ? <tr><td colSpan={13}><TableState message={t(hasFilters ? 'ws.records.callReports.employees.emptyByQuery' : 'ws.records.callReports.employees.empty', locale)} /></td></tr>
              : data.items.map((row) => <tr key={row.employee.id} tabIndex={0} onClick={() => goToDetail(row)} onKeyDown={(event) => { if (event.key === 'Enter') goToDetail(row) }}
                className="h-14 cursor-pointer border-t border-border bg-background text-foreground hover:bg-muted/35 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring">
                <td className="sticky left-0 z-10 bg-inherit px-4"><div className="flex min-w-0 items-center gap-3"><EmployeeAvatar employee={row.employee} /><div className="min-w-0"><div className="truncate font-semibold">{row.employee.display_name ?? row.employee.name}</div><div className="truncate text-xs text-muted-foreground">{row.employee.status === 'deleted' ? '—' : row.employee.username ?? row.employee.email ?? '—'}</div></div></div></td>
                <td className="px-3 text-center"><StatusBadge status={row.employee.status} /></td>
                {COLUMNS.map((column) => <td key={column.key} className="px-3 text-right font-mono tabular-nums">{formatCallMetric(row.metrics[column.key as keyof CallAgentOverviewMetrics] as number | null, column.format, locale)}</td>)}
                <td className="sticky right-0 z-10 bg-inherit px-4 text-right"><button type="button" onClick={(event) => { event.stopPropagation(); goToDetail(row) }} className="text-primary hover:underline">{t('ws.records.callReports.employees.viewDetail', locale)}</button></td>
              </tr>)}</tbody>
        </table></div>}
    {data?.coverage.status !== 'unavailable' ? <div className="flex min-h-10 flex-wrap items-center justify-between gap-3 text-[13px]">
      <span className="text-muted-foreground">{t('ws.records.callReports.employees.total', locale, { total: data?.total ?? 0 })}</span>
      <div className="flex items-center gap-2"><PageButton disabled={page <= 1} onClick={() => setPage((value) => value - 1)} label={t('ws.records.sessionReports.common.prev', locale)} /><span>{page} / {data?.pages ?? 1}</span><PageButton disabled={page >= (data?.pages ?? 1)} onClick={() => setPage((value) => value + 1)} label={t('ws.records.sessionReports.common.next', locale)} /></div>
      <div className="flex gap-2">{PER_PAGE_OPTIONS.map((option) => <button key={option} type="button" onClick={() => { setPerPage(option); setPage(1) }} className={cn('h-8 rounded-lg px-3 text-xs', perPage === option ? 'bg-foreground font-semibold text-background' : 'border border-border text-muted-foreground')}>{t('ws.records.sessionReports.common.perPage', locale, { n: option })}</button>)}</div>
    </div> : null}
  </div>
}

function FilterSelect({ value, onChange, label, options }: { value: string; onChange: (value: string) => void; label: string; options: [string, string][] }) {
  return <label className="flex h-9 items-center gap-2 rounded-lg border border-border bg-background px-3 text-xs text-muted-foreground"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)} className="bg-transparent text-foreground outline-none">{options.map(([key, text]) => <option key={key} value={key}>{text}</option>)}</select></label>
}
function SortHead({ field, sort, order, onSort, children, className }: { field: CallAgentSortField; sort: CallAgentSortField; order: SortOrder; onSort: (field: CallAgentSortField) => void; children: ReactNode; className?: string }) {
  return <th className={cn('min-w-32 px-3 text-right', className)}><button type="button" onClick={() => onSort(field)} className="inline-flex items-center gap-1 hover:text-foreground">{children}{sort === field ? order === 'desc' ? <IconArrowDown size={12} /> : <IconArrowUp size={12} /> : null}</button></th>
}
function StatusBadge({ status }: { status: CallAgentOverviewRow['employee']['status'] }) { const { locale } = useLocaleStore(); return <span className={cn('inline-flex rounded-md px-2 py-0.5 text-xs', status === 'active' ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground')}>{t(`ws.records.callReports.employees.status${status[0].toUpperCase()}${status.slice(1)}`, locale)}</span> }
function TableState({ message, onRetry }: { message: string; onRetry?: () => void }) { const { locale } = useLocaleStore(); return <div className="flex min-h-52 flex-col items-center justify-center gap-3 text-sm text-muted-foreground"><span>{message}</span>{onRetry ? <button type="button" onClick={onRetry} className="h-9 rounded-md bg-primary px-4 text-primary-foreground">{t('ws.records.callReports.overall.retry', locale)}</button> : null}</div> }
function PageButton({ disabled, onClick, label }: { disabled: boolean; onClick: () => void; label: string }) { return <button type="button" disabled={disabled} onClick={onClick} className="h-8 rounded-lg border border-border px-3 text-xs disabled:opacity-50">{label}</button> }
