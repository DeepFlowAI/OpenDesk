'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import {
  IconChevronDown,
  IconChevronLeft,
  IconChevronRight,
  IconFilter,
  IconPlus,
  IconSearch,
  IconX,
} from '@tabler/icons-react'

import { FieldOptionPill } from '@/app/components/features/field-system/field-select-pill-editors'
import { H5TicketShell } from '@/app/components/features/ticket/h5-ticket-shell'
import { WorkspaceFilterDrawer } from '@/components/workspace/workspace-filter-drawer'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { colorForSelectValue, labelForSelectValue } from '@/lib/field-select-from-unified'
import { buildSelectLookup, EMPTY_GROUP_VALUE, formatGroupLabel } from '@/lib/workspace-group'
import {
  buildH5TicketDetailUrl,
  buildH5TicketListUrl,
  buildH5TicketNewUrl,
  readH5TicketListContext,
  type H5TicketListContext,
} from '@/lib/h5-ticket-navigation'
import { cn } from '@/lib/utils'
import type { UnifiedField } from '@/models/field-definition'
import type { ConditionItem, TicketView } from '@/models/ticket-view'
import type { Ticket, TicketQueryPayload } from '@/models/ticket'
import type { ViewGroupRequestPayload } from '@/models/view-group'
import {
  useFieldReferenceEmployeeGroups,
  useFieldReferenceEmployees,
} from '@/service/use-field-reference-options'
import { useUnifiedFields } from '@/service/use-field-definitions'
import {
  useEnabledTicketViews,
  useQueryTickets,
  useTicketViewCounts,
  useTicketViewGroups,
} from '@/service/use-tickets'
import { hasPermission } from '@/utils/permissions'

const PER_PAGE = 20

type StoredFilters = {
  conditions: ConditionItem[]
  logic: 'and' | 'or'
}

export function H5TicketList() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const contentRef = useRef<HTMLDivElement>(null)
  const user = useAuthStore((state) => state.user)
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const context = useMemo(
    () => readH5TicketListContext(searchParams),
    [searchParams],
  )
  const selectedViewId: number | 'all' = context.view ? Number(context.view) : 'all'
  const page = context.page ?? 1
  const [searchInput, setSearchInput] = useState(context.q ?? '')
  const [viewSheetOpen, setViewSheetOpen] = useState(false)
  const [filterSheetOpen, setFilterSheetOpen] = useState(false)
  const [filters, setFilters] = useState<StoredFilters>({ conditions: [], logic: 'and' })

  const { data: views, isLoading: viewsLoading } = useEnabledTicketViews()
  const { data: counts } = useTicketViewCounts()
  const { data: fieldsData } = useUnifiedFields({
    domain: 'ticket',
    include_metadata: true,
    locale: isZh ? 'zh' : 'en',
  })
  const { data: employeesData } = useFieldReferenceEmployees({ page: 1, per_page: 1000 })
  const { data: groupsLookupData } = useFieldReferenceEmployeeGroups({ page: 1, per_page: 1000 })

  useEffect(() => setSearchInput(context.q ?? ''), [context.q])

  const filterStorageKey = `h5_ticket_filters_${user?.tenant_id ?? 'unknown'}`
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(filterStorageKey)
      if (raw) setFilters(JSON.parse(raw) as StoredFilters)
    } catch {
      setFilters({ conditions: [], logic: 'and' })
    }
  }, [filterStorageKey])

  const persistFilters = useCallback((next: StoredFilters) => {
    setFilters(next)
    try {
      sessionStorage.setItem(filterStorageKey, JSON.stringify(next))
    } catch {
      // Session storage may be unavailable in restricted WebViews.
    }
  }, [filterStorageKey])

  const activeView: TicketView | null = useMemo(() => {
    if (selectedViewId === 'all') return null
    return views?.find((view) => view.id === selectedViewId) ?? null
  }, [selectedViewId, views])
  const allFields = useMemo(() => fieldsData?.items ?? [], [fieldsData])
  const filterFields = useMemo(
    () => allFields.filter((field) => field.source !== 'metadata'),
    [allFields],
  )
  const fieldByKey = useMemo(() => {
    const result = new Map<string, UnifiedField>()
    for (const field of allFields) if (field.key) result.set(field.key, field)
    return result
  }, [allFields])
  const groupField = useMemo(
    () => activeView?.group_field_id == null ? null : allFields.find((field) => field.id === activeView.group_field_id) ?? null,
    [activeView?.group_field_id, allFields],
  )
  const groupSelectLookup = useMemo(() => buildSelectLookup(groupField), [groupField])
  const countByView = useMemo(
    () => new Map((counts?.items ?? []).map((item) => [item.view_id, item.count])),
    [counts],
  )
  const employeeById = useMemo(
    () => new Map((employeesData?.items ?? []).map((item) => [item.id, item.nickname || item.name || item.username])),
    [employeesData],
  )
  const groupById = useMemo(
    () => new Map((groupsLookupData?.items ?? []).map((item) => [item.id, item.name])),
    [groupsLookupData],
  )

  const groupsEnabled = selectedViewId !== 'all' && activeView?.group_field_id != null
  const groupsRequest: ViewGroupRequestPayload = useMemo(() => ({
    search: context.q,
    temp_conditions: filters.conditions.length ? filters.conditions : undefined,
    temp_condition_logic: filters.conditions.length ? filters.logic : undefined,
  }), [context.q, filters])
  const { data: groupsData, isLoading: groupsLoading } = useTicketViewGroups(
    selectedViewId === 'all' ? null : selectedViewId,
    groupsRequest,
    groupsEnabled,
  )

  const queryPayload: TicketQueryPayload = useMemo(() => ({
    view_id: selectedViewId === 'all' ? null : selectedViewId,
    search: context.q,
    temp_conditions: filters.conditions.length ? filters.conditions : undefined,
    temp_condition_logic: filters.conditions.length ? filters.logic : undefined,
    group_value: groupsEnabled ? context.group : undefined,
    page,
    per_page: PER_PAGE,
  }), [context.group, context.q, filters, groupsEnabled, page, selectedViewId])
  const ticketsQuery = useQueryTickets(queryPayload)

  const navigate = useCallback((next: H5TicketListContext) => {
    router.replace(buildH5TicketListUrl(next), { scroll: false })
  }, [router])

  const selectView = (view: number | 'all') => {
    persistFilters({ conditions: [], logic: 'and' })
    setSearchInput('')
    navigate({ view: view === 'all' ? undefined : String(view) })
    setViewSheetOpen(false)
  }
  const submitSearch = () => navigate({ ...context, q: searchInput.trim() || undefined, page: undefined })
  const clearSearch = () => {
    setSearchInput('')
    navigate({ ...context, q: undefined, page: undefined })
  }
  const changePage = (nextPage: number) => {
    navigate({ ...context, page: nextPage > 1 ? nextPage : undefined })
    contentRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }
  const clearSearchAndFilters = () => {
    persistFilters({ conditions: [], logic: 'and' })
    setSearchInput('')
    navigate({ ...context, q: undefined, group: undefined, page: undefined })
  }

  const hasFilters = filters.conditions.length > 0
  const hasNarrowing = hasFilters || Boolean(context.q) || Boolean(context.group)
  const totalPages = ticketsQuery.data?.pages ?? 0
  const canCreate = hasPermission(user, 'ticket.workspace.create')

  return (
    <H5TicketShell
      title={isZh ? '工单' : 'Tickets'}
      action={canCreate ? (
        <button
          type="button"
          aria-label={isZh ? '新建工单' : 'Create ticket'}
          onClick={() => router.push(buildH5TicketNewUrl(context))}
          className="flex h-11 min-w-11 items-center justify-center rounded-md active:opacity-60"
        >
          <IconPlus size={22} />
        </button>
      ) : null}
      contentClassName="[scrollbar-gutter:stable]"
    >
      <div ref={contentRef} className="flex min-h-full flex-col gap-3 p-4 pb-6">
        <button
          type="button"
          onClick={() => setViewSheetOpen(true)}
          className="flex h-11 w-full items-center justify-between rounded-lg border border-border bg-background px-4 text-sm active:opacity-60"
        >
          <span className="truncate font-medium">
            {selectedViewId === 'all' ? (isZh ? '全部' : 'All') : activeView?.name ?? (isZh ? '全部' : 'All')}
          </span>
          <span className="flex items-center gap-2 text-muted-foreground">
            {selectedViewId === 'all' ? counts?.total_count : countByView.get(selectedViewId)}
            <IconChevronDown size={18} />
          </span>
        </button>

        <H5TicketSearchForm
          isZh={isZh}
          value={searchInput}
          filterCount={filters.conditions.length}
          onChange={setSearchInput}
          onSubmit={submitSearch}
          onClear={clearSearch}
          onFilter={() => setFilterSheetOpen(true)}
        />

        {groupsEnabled && (
          <div className="flex min-h-8 gap-2 overflow-x-auto pb-1">
            <GroupChip
              label={isZh ? '全部' : 'All'}
              count={groupsData?.total ?? 0}
              active={!context.group}
              onClick={() => navigate({ ...context, group: undefined, page: undefined })}
            />
            {groupsLoading ? <div className="h-8 w-24 animate-pulse rounded-full bg-muted" /> : groupsData?.items.map((item, index) => {
              const value = item.value == null ? EMPTY_GROUP_VALUE : String(item.value)
              return (
                <GroupChip
                  key={`${value}-${index}`}
                  label={formatGroupLabel(item.value, groupField, groupSelectLookup, locale)}
                  count={item.count}
                  active={context.group === value}
                  onClick={() => navigate({ ...context, group: value, page: undefined })}
                />
              )
            })}
          </div>
        )}

        <section className="flex flex-1 flex-col gap-2" aria-live="polite">
          {ticketsQuery.isLoading ? (
            Array.from({ length: 5 }, (_, index) => <TicketCardSkeleton key={index} />)
          ) : ticketsQuery.isError ? (
            <CenteredState
              title={isZh ? '加载失败，请重试' : 'Failed to load. Please try again'}
              actionLabel={isZh ? '重试' : 'Retry'}
              onAction={() => void ticketsQuery.refetch()}
            />
          ) : !ticketsQuery.data?.items.length ? (
            <CenteredState
              title={hasNarrowing ? (isZh ? '未找到匹配的工单' : 'No matching tickets') : (isZh ? '暂无工单' : 'No tickets yet')}
              actionLabel={hasNarrowing ? (isZh ? '清除搜索与筛选' : 'Clear search and filters') : canCreate ? (isZh ? '新建工单' : 'Create ticket') : undefined}
              onAction={hasNarrowing ? clearSearchAndFilters : canCreate ? () => router.push(buildH5TicketNewUrl(context)) : undefined}
            />
          ) : ticketsQuery.data.items.map((ticket) => (
            <TicketCard
              key={ticket.id}
              ticket={ticket}
              isZh={isZh}
              statusField={fieldByKey.get('status')}
              priorityField={fieldByKey.get('priority')}
              employeeName={ticket.agent_id ? employeeById.get(ticket.agent_id) : undefined}
              groupName={ticket.assignee_group_id ? groupById.get(ticket.assignee_group_id) : undefined}
              onClick={() => router.push(buildH5TicketDetailUrl(ticket.id, context))}
            />
          ))}
        </section>

        {totalPages > 0 && (
          <nav className="flex items-center justify-between pt-2 text-xs">
            <PaginationButton disabled={page <= 1} onClick={() => changePage(page - 1)}>
              <IconChevronLeft size={16} /> {isZh ? '上一页' : 'Previous'}
            </PaginationButton>
            <span>{isZh ? `第 ${page} / ${totalPages} 页` : `Page ${page} / ${totalPages}`}</span>
            <PaginationButton disabled={page >= totalPages} onClick={() => changePage(page + 1)}>
              {isZh ? '下一页' : 'Next'} <IconChevronRight size={16} />
            </PaginationButton>
          </nav>
        )}
      </div>

      <Sheet open={viewSheetOpen} onOpenChange={setViewSheetOpen}>
        <SheetContent side="bottom" className="max-h-[80dvh] rounded-t-xl p-0" showCloseButton={false}>
          <SheetHeader className="border-b border-border px-4 py-4">
            <SheetTitle>{isZh ? '系统视图' : 'System views'}</SheetTitle>
          </SheetHeader>
          <div className="min-h-0 overflow-y-auto p-2 pb-[max(12px,env(safe-area-inset-bottom))]">
            <ViewRow label={isZh ? '全部' : 'All'} count={counts?.total_count ?? 0} active={selectedViewId === 'all'} onClick={() => selectView('all')} />
            {!viewsLoading && views?.map((view) => (
              <ViewRow key={view.id} label={view.name} count={countByView.get(view.id) ?? 0} active={selectedViewId === view.id} onClick={() => selectView(view.id)} />
            ))}
          </div>
        </SheetContent>
      </Sheet>

      {filterSheetOpen && (
        <WorkspaceFilterDrawer
          locale={locale}
          fields={filterFields}
          conditions={filters.conditions}
          conditionLogic={filters.logic}
          onApply={(conditions, logic) => {
            persistFilters({ conditions, logic })
            navigate({ ...context, page: undefined })
          }}
          onClose={() => setFilterSheetOpen(false)}
          presentation="bottom"
        />
      )}
    </H5TicketShell>
  )
}

type H5TicketSearchFormProps = {
  isZh: boolean
  value: string
  filterCount: number
  onChange: (value: string) => void
  onSubmit: () => void
  onClear: () => void
  onFilter: () => void
}

export function H5TicketSearchForm({
  isZh,
  value,
  filterCount,
  onChange,
  onSubmit,
  onClear,
  onFilter,
}: H5TicketSearchFormProps) {
  const searchLabel = isZh ? '搜索工单' : 'Search tickets'
  const hasFilters = filterCount > 0

  return (
    <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); onSubmit() }}>
      <div className="relative min-w-0 flex-1">
        <button
          type="submit"
          aria-label={searchLabel}
          className="absolute left-0 top-0 flex h-10 w-10 items-center justify-center text-muted-foreground active:opacity-60"
        >
          <IconSearch size={18} />
        </button>
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={isZh ? '搜索工单…' : 'Search tickets…'}
          aria-label={searchLabel}
          enterKeyHint="search"
          className="h-10 w-full rounded-lg border border-border bg-secondary pl-10 pr-9 text-sm outline-none focus:border-ring"
        />
        {value && (
          <button
            type="button"
            onClick={onClear}
            aria-label={isZh ? '清除搜索' : 'Clear search'}
            className="absolute right-0 top-0 flex h-10 w-10 items-center justify-center text-muted-foreground active:opacity-60"
          >
            <IconX size={17} />
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={onFilter}
        className={cn(
          'flex h-10 shrink-0 items-center gap-1.5 rounded-lg border px-3 text-sm active:opacity-60',
          hasFilters ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-background',
        )}
      >
        <IconFilter size={16} />
        {isZh ? '筛选' : 'Filter'}
        {hasFilters && <span>{filterCount}</span>}
      </button>
    </form>
  )
}

function TicketCard({ ticket, isZh, statusField, priorityField, employeeName, groupName, onClick }: {
  ticket: Ticket
  isZh: boolean
  statusField?: UnifiedField
  priorityField?: UnifiedField
  employeeName?: string
  groupName?: string
  onClick: () => void
}) {
  const status = labelForSelectValue(statusField, ticket.status)
  const priority = ticket.priority ? labelForSelectValue(priorityField, ticket.priority) : null
  const assigned = [groupName, employeeName].filter(Boolean).join(' · ') || (isZh ? '未分配' : 'Unassigned')
  return (
    <button type="button" onClick={onClick} className="flex w-full flex-col gap-2 rounded-lg border border-border bg-card p-4 text-left transition-colors active:bg-muted">
      <span className="truncate text-[15px] font-semibold">{ticket.title || (isZh ? '未命名工单' : 'Untitled ticket')}</span>
      {ticket.ticket_number && <span className="text-xs text-muted-foreground">#{ticket.ticket_number.replace(/^#/, '')}</span>}
      <span className="flex flex-wrap gap-2">
        <FieldOptionPill label={status} color={colorForSelectValue(statusField, ticket.status)} />
        {priority && <FieldOptionPill label={priority} color={colorForSelectValue(priorityField, ticket.priority ?? '')} />}
      </span>
      <span className="truncate text-xs text-muted-foreground">{assigned}</span>
      <time className="text-xs text-muted-foreground" dateTime={ticket.updated_at}>
        {new Intl.DateTimeFormat(isZh ? 'zh-CN' : 'en-US', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(ticket.updated_at))}
      </time>
    </button>
  )
}

function GroupChip({ label, count, active, onClick }: { label: string; count: number; active: boolean; onClick: () => void }) {
  return <button type="button" onClick={onClick} className={cn('flex h-8 shrink-0 items-center gap-1 rounded-full px-3 text-xs active:opacity-60', active ? 'bg-primary text-primary-foreground' : 'bg-secondary text-foreground')}><span>{label}</span><span className={active ? 'text-primary-foreground/70' : 'text-muted-foreground'}>{count}</span></button>
}

function ViewRow({ label, count, active, onClick }: { label: string; count: number; active: boolean; onClick: () => void }) {
  return <button type="button" onClick={onClick} className={cn('flex h-12 w-full items-center justify-between rounded-lg px-3 text-sm', active && 'bg-muted font-semibold')}><span className="truncate">{label}</span><span className="text-muted-foreground">{count}</span></button>
}

function PaginationButton({ disabled, onClick, children }: { disabled: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button type="button" disabled={disabled} onClick={onClick} className="flex h-10 items-center gap-1 rounded-lg border border-border px-3 disabled:opacity-40">{children}</button>
}

function CenteredState({ title, actionLabel, onAction }: { title: string; actionLabel?: string; onAction?: () => void }) {
  return <div className="flex flex-1 flex-col items-center justify-center gap-3 py-12 text-center"><p className="text-sm text-muted-foreground">{title}</p>{actionLabel && onAction && <button type="button" onClick={onAction} className="h-10 rounded-lg border border-border px-4 text-sm font-medium">{actionLabel}</button>}</div>
}

function TicketCardSkeleton() {
  return <div className="flex flex-col gap-3 rounded-lg border border-border p-4"><div className="h-4 w-2/3 animate-pulse rounded bg-muted" /><div className="h-3 w-1/3 animate-pulse rounded bg-muted" /><div className="h-6 w-24 animate-pulse rounded bg-muted" /><div className="h-3 w-1/2 animate-pulse rounded bg-muted" /></div>
}
