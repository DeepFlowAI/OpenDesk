'use client'

import { useState, useCallback } from 'react'
import { IconSearch, IconLoader2, IconCalendar, IconChevronDown, IconChevronRight } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useSessionRecords } from '@/service/use-session-records'
import { useEmployees } from '@/service/use-employees'
import { useSatisfactionFilterOptions } from '@/service/use-satisfaction-survey'
import { useAuthStore } from '@/context/auth-store'
import { DateInput } from '@/components/ui/time-input'
import type { SessionRecord, SessionRecordFilters } from '@/models/session-record'

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  return d.toLocaleString('sv-SE').replace('T', ' ')
}

function formatDuration(startStr: string | null, endStr: string | null): string {
  if (!startStr) return '-'
  const start = new Date(startStr).getTime()
  const end = endStr ? new Date(endStr).getTime() : Date.now()
  const diff = Math.max(0, Math.floor((end - start) / 1000))
  const h = Math.floor(diff / 3600)
  const m = Math.floor((diff % 3600) / 60)
  const s = diff % 60
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}

function satisfactionLabel(status: string, locale: string) {
  if (status === 'none') return locale === 'zh' ? '未评价' : 'Not rated'
  if (status === 'invited') return locale === 'zh' ? '已邀请' : 'Invited'
  if (status === 'submitted') return locale === 'zh' ? '已评价' : 'Rated'
  return status
}

function SatisfactionSummaryCell({ record, locale }: { record: SessionRecord; locale: string }) {
  const summary = record.satisfaction
  if (!summary || summary.status === 'none') {
    return <span className="text-sm text-muted-foreground">{satisfactionLabel('none', locale)}</span>
  }
  if (summary.status === 'invited') {
    return (
      <span className="inline-flex items-center rounded-full bg-[#FEF3C7] px-2 py-0.5 text-xs font-medium text-[#92400E]">
        {satisfactionLabel('invited', locale)}
      </span>
    )
  }
  return (
    <div className="flex max-w-[220px] flex-wrap gap-1">
      {summary.labels.length > 0 ? summary.labels.map((label) => (
        <span key={label} className="inline-flex rounded-full bg-muted px-2 py-0.5 text-xs text-foreground">
          {label}
        </span>
      )) : (
        <span className="inline-flex rounded-full bg-muted px-2 py-0.5 text-xs text-foreground">
          {satisfactionLabel(summary.status, locale)}
        </span>
      )}
    </div>
  )
}

type Props = {
  onSelectRecord: (record: SessionRecord) => void
}

const PER_PAGE_OPTIONS = [20, 50, 100]

export function SessionTable({ onSelectRecord }: Props) {
  const { locale } = useLocaleStore()
  const { user } = useAuthStore()
  const isAdmin = user?.roles?.includes('admin') ?? false

  const now = new Date()
  const sevenDaysAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)

  const [filters, setFilters] = useState<SessionRecordFilters>({
    page: 1,
    per_page: 20,
    start_date: sevenDaysAgo.toISOString(),
    end_date: now.toISOString(),
  })
  const [draftKeyword, setDraftKeyword] = useState('')
  const [draftStartDate, setDraftStartDate] = useState(sevenDaysAgo.toISOString().slice(0, 10))
  const [draftEndDate, setDraftEndDate] = useState(now.toISOString().slice(0, 10))
  const [draftAgentId, setDraftAgentId] = useState<number | undefined>(undefined)
  const [draftSatisfactionStatus, setDraftSatisfactionStatus] = useState('')
  const [draftResolved, setDraftResolved] = useState('')
  const [draftServiceOption, setDraftServiceOption] = useState('')
  const [draftServiceLabel, setDraftServiceLabel] = useState('')
  const [draftProductOption, setDraftProductOption] = useState('')
  const [draftProductLabel, setDraftProductLabel] = useState('')
  const [satisfactionFiltersExpanded, setSatisfactionFiltersExpanded] = useState(false)

  const { data, isLoading } = useSessionRecords(filters)
  const { data: satisfactionOptions } = useSatisfactionFilterOptions()
  const hasSatisfactionFilters = satisfactionOptions?.configured === true
  const satisfactionFilterActiveCount = [
    draftSatisfactionStatus,
    draftResolved,
    draftServiceOption,
    draftServiceLabel,
    draftProductOption,
    draftProductLabel,
  ].filter(Boolean).length
  // All active employees who may appear as 接待 (agent or admin; role=agent alone omits admin-only staff)
  const { data: employeesData } = useEmployees(
    { per_page: 200, status: 'active' },
    { enabled: isAdmin }
  )

  const handleSearch = useCallback(() => {
    setFilters({
      ...filters,
      page: 1,
      start_date: draftStartDate ? new Date(draftStartDate + 'T00:00:00').toISOString() : undefined,
      end_date: draftEndDate ? new Date(draftEndDate + 'T23:59:59').toISOString() : undefined,
      agent_id: draftAgentId,
      keyword: draftKeyword || undefined,
      satisfaction_status: draftSatisfactionStatus || undefined,
      satisfaction_resolved: draftResolved || undefined,
      satisfaction_service_option: draftServiceOption || undefined,
      satisfaction_service_label: draftServiceLabel || undefined,
      satisfaction_product_option: draftProductOption || undefined,
      satisfaction_product_label: draftProductLabel || undefined,
    })
  }, [filters, draftStartDate, draftEndDate, draftAgentId, draftKeyword, draftSatisfactionStatus, draftResolved, draftServiceOption, draftServiceLabel, draftProductOption, draftProductLabel])

  const handleReset = useCallback(() => {
    const resetStart = sevenDaysAgo.toISOString().slice(0, 10)
    const resetEnd = now.toISOString().slice(0, 10)
    setDraftKeyword('')
    setDraftStartDate(resetStart)
    setDraftEndDate(resetEnd)
    setDraftAgentId(undefined)
    setDraftSatisfactionStatus('')
    setDraftResolved('')
    setDraftServiceOption('')
    setDraftServiceLabel('')
    setDraftProductOption('')
    setDraftProductLabel('')
    setSatisfactionFiltersExpanded(false)
    setFilters({
      page: 1,
      per_page: 20,
      start_date: new Date(resetStart + 'T00:00:00').toISOString(),
      end_date: new Date(resetEnd + 'T23:59:59').toISOString(),
    })
  }, [])

  const handleRowClick = useCallback(
    (record: SessionRecord, e: React.MouseEvent) => {
      const selection = window.getSelection()
      if (selection && selection.toString().length > 0) return
      onSelectRecord(record)
    },
    [onSelectRecord]
  )

  const items = data?.items || []
  const total = data?.total || 0
  const pages = data?.pages || 0

  return (
    <div className="flex h-full min-w-0 flex-col">
      {/* Filter bar — horizontal padding matches .pen Content Area (24px) */}
      <div className="flex shrink-0 flex-wrap items-end gap-3 px-6 py-4">
        {/* Date range — single grouped control (Date Range Picker) */}
        <div className="flex flex-col gap-1.5">
          <span className="text-xs text-muted-foreground" id="session-records-date-range-label">
            {t('ws.records.sessions.filter.dateRange', locale)}
          </span>
          <div
            className="flex h-9 max-w-md min-w-0 items-center gap-1.5 rounded-lg border border-border bg-background pl-2.5 pr-2"
            role="group"
            aria-labelledby="session-records-date-range-label"
          >
            <IconCalendar size={16} className="shrink-0 text-muted-foreground" aria-hidden />
            <DateInput
              value={draftStartDate}
              onChange={(e) => setDraftStartDate(e.target.value)}
              className="h-7 w-[min(8.5rem,100%)] min-w-0 flex-1 border-0 bg-transparent py-0 text-sm text-foreground shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 md:text-sm"
            />
            <span className="shrink-0 text-sm text-muted-foreground">~</span>
            <DateInput
              value={draftEndDate}
              onChange={(e) => setDraftEndDate(e.target.value)}
              className="h-7 w-[min(8.5rem,100%)] min-w-0 flex-1 border-0 bg-transparent py-0 text-sm text-foreground shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 md:text-sm"
            />
          </div>
        </div>

        {/* Agent select */}
        {isAdmin && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">
              {t('ws.records.sessions.filter.agent', locale)}
            </label>
            <select
              value={draftAgentId ?? ''}
              onChange={(e) => setDraftAgentId(e.target.value ? Number(e.target.value) : undefined)}
              className="h-9 min-w-[160px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="">{t('ws.records.sessions.filter.allAgents', locale)}</option>
              {employeesData?.items?.map((emp: { id: number; name: string }) => (
                <option key={emp.id} value={emp.id}>
                  {emp.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Keyword */}
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">&nbsp;</label>
          <div className="relative">
            <IconSearch size={16} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={draftKeyword}
              onChange={(e) => setDraftKeyword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder={t('ws.records.sessions.filter.keyword', locale)}
              className="h-9 w-[260px] rounded-md border border-border bg-background pl-8 pr-3 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        </div>

        {/* Satisfaction filters */}
        {hasSatisfactionFilters && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">&nbsp;</label>
            <button
              type="button"
              onClick={() => setSatisfactionFiltersExpanded((expanded) => !expanded)}
              aria-expanded={satisfactionFiltersExpanded}
              aria-controls="session-records-satisfaction-filters"
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border bg-background px-3 text-sm text-foreground transition-colors hover:bg-accent"
            >
              {satisfactionFiltersExpanded
                ? <IconChevronDown size={16} className="shrink-0 text-muted-foreground" />
                : <IconChevronRight size={16} className="shrink-0 text-muted-foreground" />}
              <span>{t('ws.records.sessions.filter.satisfactionGroup', locale)}</span>
              {satisfactionFilterActiveCount > 0 && (
                <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary/10 px-1.5 text-xs font-medium text-primary">
                  {satisfactionFilterActiveCount}
                </span>
              )}
            </button>
          </div>
        )}

        {hasSatisfactionFilters && satisfactionFiltersExpanded && (
          <div id="session-records-satisfaction-filters" className="contents">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-muted-foreground">
                {t('ws.records.sessions.filter.satisfactionStatus', locale)}
              </label>
              <select
                value={draftSatisfactionStatus}
                onChange={(e) => setDraftSatisfactionStatus(e.target.value)}
                className="h-9 min-w-[130px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
              >
                <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
                <option value="none">{t('ws.records.sessions.satisfaction.none', locale)}</option>
                <option value="invited">{t('ws.records.sessions.satisfaction.invited', locale)}</option>
                <option value="submitted">{t('ws.records.sessions.satisfaction.submitted', locale)}</option>
              </select>
            </div>

            {satisfactionOptions.show_resolution && (
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">
                  {t('ws.records.sessions.filter.resolved', locale)}
                </label>
                <select
                  value={draftResolved}
                  onChange={(e) => setDraftResolved(e.target.value)}
                  className="h-9 min-w-[120px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
                  <option value="resolved">{t('ws.records.sessions.satisfaction.resolved', locale)}</option>
                  <option value="unresolved">{t('ws.records.sessions.satisfaction.unresolved', locale)}</option>
                </select>
              </div>
            )}

            {satisfactionOptions.service_options?.length ? (
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">
                  {t('ws.records.sessions.filter.serviceRating', locale)}
                </label>
                <select
                  value={draftServiceOption}
                  onChange={(e) => setDraftServiceOption(e.target.value)}
                  className="h-9 min-w-[150px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
                  {satisfactionOptions.service_options.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
              </div>
            ) : null}

            {satisfactionOptions.service_labels?.length ? (
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">
                  {t('ws.records.sessions.filter.serviceLabel', locale)}
                </label>
                <select
                  value={draftServiceLabel}
                  onChange={(e) => setDraftServiceLabel(e.target.value)}
                  className="h-9 min-w-[150px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
                  {satisfactionOptions.service_labels.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
              </div>
            ) : null}

            {satisfactionOptions.product_options?.length ? (
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">
                  {t('ws.records.sessions.filter.productRating', locale)}
                </label>
                <select
                  value={draftProductOption}
                  onChange={(e) => setDraftProductOption(e.target.value)}
                  className="h-9 min-w-[150px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
                  {satisfactionOptions.product_options.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
              </div>
            ) : null}

            {satisfactionOptions.product_labels?.length ? (
              <div className="flex flex-col gap-1">
                <label className="text-xs text-muted-foreground">
                  {t('ws.records.sessions.filter.productLabel', locale)}
                </label>
                <select
                  value={draftProductLabel}
                  onChange={(e) => setDraftProductLabel(e.target.value)}
                  className="h-9 min-w-[150px] rounded-md border border-border bg-background px-2.5 text-sm text-foreground outline-none focus:ring-1 focus:ring-ring"
                >
                  <option value="">{t('ws.records.sessions.filter.all', locale)}</option>
                  {satisfactionOptions.product_labels.map((option) => (
                    <option key={option.key} value={option.key}>{option.label}</option>
                  ))}
                </select>
              </div>
            ) : null}
          </div>
        )}

        {/* Buttons */}
        <div className="flex gap-2">
          <button
            onClick={handleSearch}
            className="h-9 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {t('ws.records.sessions.filter.search', locale)}
          </button>
          <button
            onClick={handleReset}
            className="h-9 rounded-md border border-border bg-background px-4 text-sm text-foreground transition-colors hover:bg-accent"
          >
            {t('ws.records.sessions.filter.reset', locale)}
          </button>
        </div>
      </div>

      {/* Table — outer frame + horizontal inset so rules do not run flush to the card edges (.pen) */}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col px-6 pt-4">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-border bg-background">
          <div className="min-h-0 flex-1 overflow-auto">
            {isLoading ? (
              <div className="flex h-full min-h-[200px] items-center justify-center">
                <IconLoader2 size={24} className="animate-spin text-muted-foreground" />
              </div>
            ) : items.length === 0 ? (
              <div className="flex h-full min-h-[200px] flex-col items-center justify-center gap-2 px-4 text-muted-foreground">
                <p className="text-sm">
                  {filters.keyword || filters.agent_id
                    ? t('ws.records.sessions.emptyFiltered', locale)
                    : t('ws.records.sessions.empty', locale)}
                </p>
              </div>
            ) : (
              <table className="w-max min-w-full border-separate border-spacing-0 table-auto">
                <thead>
                  <tr>
                <th className="sticky top-0 z-10 rounded-tl-lg border-b border-border bg-muted py-3 pl-4 pr-3 text-left text-xs font-semibold text-muted-foreground">
                  {t('ws.records.sessions.col.visitor', locale)}
                </th>
                <th className="sticky top-0 z-10 w-[120px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                  {t('ws.records.sessions.col.shareCode', locale)}
                </th>
                <th className="sticky top-0 z-10 w-[100px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                  {t('ws.records.sessions.col.channelType', locale)}
                </th>
                <th className="sticky top-0 z-10 w-[150px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                  {t('ws.records.sessions.col.channelName', locale)}
                </th>
                <th className="sticky top-0 z-10 w-[120px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                  {t('ws.records.sessions.col.agent', locale)}
                </th>
                <th className="sticky top-0 z-10 w-[180px] border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                  {t('ws.records.sessions.col.satisfaction', locale)}
                </th>
                <th className="sticky top-0 z-10 min-w-[170px] whitespace-nowrap border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                  {t('ws.records.sessions.col.startTime', locale)}
                </th>
                <th className="sticky top-0 z-10 min-w-[170px] whitespace-nowrap border-b border-border bg-muted px-3 py-3 text-left text-xs font-semibold text-muted-foreground">
                  {t('ws.records.sessions.col.endTime', locale)}
                </th>
                <th className="sticky top-0 z-10 w-[100px] rounded-tr-lg border-b border-border bg-muted py-3 pl-3 pr-4 text-left text-xs font-semibold text-muted-foreground">
                  {t('ws.records.sessions.col.duration', locale)}
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((record) => (
                <tr
                  key={record.id}
                  onClick={(e) => handleRowClick(record, e)}
                  className="cursor-pointer transition-colors hover:bg-accent/30"
                >
                  <td className="border-b border-border py-3 pl-4 pr-3 text-sm text-foreground">
                    {record.visitor?.name || '-'}
                  </td>
                  <td className="border-b border-border px-3 py-3 font-mono text-sm text-muted-foreground">
                    {record.share_code || record.public_id || '-'}
                  </td>
                  <td className="border-b border-border px-3 py-3 text-sm text-muted-foreground">
                    {record.channel?.channel_type || '-'}
                  </td>
                  <td className="border-b border-border px-3 py-3 text-sm text-muted-foreground">
                    {record.channel?.name || '-'}
                  </td>
                  <td className="border-b border-border px-3 py-3 text-sm text-muted-foreground">
                    {record.agent?.display_name || record.agent?.name || '-'}
                  </td>
                  <td className="border-b border-border px-3 py-3">
                    <SatisfactionSummaryCell record={record} locale={locale} />
                  </td>
                  <td className="min-w-[170px] whitespace-nowrap border-b border-border px-3 py-3 text-sm text-muted-foreground">
                    {formatDateTime(record.started_at)}
                  </td>
                  <td className="min-w-[170px] whitespace-nowrap border-b border-border px-3 py-3 text-sm text-muted-foreground">
                    {record.ended_at
                      ? formatDateTime(record.ended_at)
                      : (
                        <span className="inline-flex items-center rounded-full bg-success/10 px-2 py-0.5 text-xs font-medium text-success">
                          {t('ws.records.sessions.status.active', locale)}
                        </span>
                      )}
                  </td>
                  <td className="border-b border-border py-3 pl-3 pr-4 text-sm text-muted-foreground">
                    {formatDuration(record.started_at, record.ended_at)}
                  </td>
                </tr>
              ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {/* Pagination */}
      {total > 0 && (
        <div className="flex shrink-0 items-center justify-between px-6 py-3">
          <span className="text-xs text-muted-foreground">
            {t('ws.records.sessions.pagination.total', locale, { total: String(total) })}
          </span>
          <div className="flex items-center gap-2">
            <select
              value={filters.per_page}
              onChange={(e) => setFilters({ ...filters, page: 1, per_page: Number(e.target.value) })}
              className="h-8 rounded-md border border-border bg-background px-2 text-xs outline-none"
            >
              {PER_PAGE_OPTIONS.map((n) => (
                <option key={n} value={n}>{n} / page</option>
              ))}
            </select>
            <div className="flex gap-1">
              {Array.from({ length: Math.min(pages, 7) }, (_, i) => {
                let pageNum: number
                if (pages <= 7) {
                  pageNum = i + 1
                } else if (filters.page <= 4) {
                  pageNum = i + 1
                } else if (filters.page >= pages - 3) {
                  pageNum = pages - 6 + i
                } else {
                  pageNum = filters.page - 3 + i
                }
                return (
                  <button
                    key={pageNum}
                    onClick={() => setFilters({ ...filters, page: pageNum })}
                    className={cn(
                      'flex h-8 min-w-8 items-center justify-center rounded-md px-2 text-xs transition-colors',
                      filters.page === pageNum
                        ? 'bg-primary text-primary-foreground'
                        : 'border border-border text-foreground hover:bg-accent'
                    )}
                  >
                    {pageNum}
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
