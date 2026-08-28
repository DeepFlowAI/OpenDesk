'use client'

import {
  IconAdjustmentsHorizontal, IconCalendar, IconChevronDown, IconChevronUp, IconColumns3,
  IconDownload, IconLoader2, IconSearch,
} from '@tabler/icons-react'

import { DateInput } from '@/components/ui/time-input'
import type { CallRecordFilterOptionsResponse } from '@/models/call-center'
import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'

import type { CallRecordFilterDraft } from './use-call-record-list'
import { CallRecordSearchableSelect } from './call-record-searchable-select'
import { CallRecordMoreFilters } from './call-record-more-filters'

type Props = {
  locale: Locale
  draft: CallRecordFilterDraft
  onChange: (next: CallRecordFilterDraft) => void
  onSearch: () => void
  searching: boolean
  onReset: () => void
  options?: CallRecordFilterOptionsResponse
  canFilterByOwnership: boolean
  moreFilterCount: number
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
  canExport: boolean
  exporting: boolean
  onExport: () => void
  onColumns: () => void
  hasColumnOverride: boolean
}

const controlClass = 'h-9 rounded-md border border-border bg-background px-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring'

export function CallRecordFilterBar(props: Props) {
  const { locale, draft, options, expanded } = props
  const patch = (next: Partial<CallRecordFilterDraft>) => props.onChange({ ...draft, ...next })
  const agentOptions = (options?.agents ?? []).map((agent) => ({
    value: String(agent.id), label: agent.name,
  }))

  return (
    <div className="shrink-0 border-b border-border bg-background px-6 py-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-1.5">
          <span className="text-xs text-muted-foreground" id="call-records-date-range-label">
            {t('ws.records.calls.filter.dateRange', locale)}
          </span>
          <div
            className="flex h-9 max-w-md min-w-0 items-center gap-1.5 rounded-lg border border-border bg-background pl-2.5 pr-2"
            role="group"
            aria-labelledby="call-records-date-range-label"
          >
            <IconCalendar size={16} className="shrink-0 text-muted-foreground" aria-hidden />
            <DateInput
              value={draft.startDate}
              onChange={(event) => patch({ startDate: event.target.value })}
              aria-label={t('ws.records.calls.filter.startDate', locale)}
              className="h-7 w-[min(8.5rem,100%)] min-w-0 flex-1 border-0 bg-transparent py-0 text-sm text-foreground shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 md:text-sm"
            />
            <span className="shrink-0 text-sm text-muted-foreground">~</span>
            <DateInput
              value={draft.endDate}
              onChange={(event) => patch({ endDate: event.target.value })}
              aria-label={t('ws.records.calls.filter.endDate', locale)}
              className="h-7 w-[min(8.5rem,100%)] min-w-0 flex-1 border-0 bg-transparent py-0 text-sm text-foreground shadow-none focus-visible:ring-0 focus-visible:ring-offset-0 md:text-sm"
            />
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-xs text-muted-foreground">
            {t('ws.records.calls.filter.direction', locale)}
          </label>
          <select value={draft.direction} onChange={(event) => patch({ direction: event.target.value })} className={controlClass}>
            <option value="">{t('ws.records.calls.filter.allDirections', locale)}</option>
            <option value="inbound">{t('ws.records.calls.option.direction.inbound', locale)}</option>
            <option value="outbound">{t('ws.records.calls.option.direction.outbound', locale)}</option>
          </select>
        </div>
        {props.canFilterByOwnership && (
          <div className="flex flex-col gap-1">
            <label className="text-xs text-muted-foreground">
              {t('ws.records.calls.filter.lastServingAgent', locale)}
            </label>
            <CallRecordSearchableSelect
              value={draft.lastServingAgentId}
              onChange={(value) => patch({ lastServingAgentId: value })}
              options={agentOptions}
              placeholder={t('ws.records.calls.filter.all', locale)}
              searchPlaceholder={t('ws.records.calls.filter.searchOption', locale)}
              emptyText={t('ws.records.calls.filter.emptyOptions', locale)}
              className="w-[180px]"
            />
          </div>
        )}
        <div className="flex min-w-[220px] flex-1 flex-col gap-1 sm:max-w-[300px]">
          <label className="text-xs text-muted-foreground">&nbsp;</label>
          <div className="relative">
            <IconSearch size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={draft.keyword}
              onChange={(event) => patch({ keyword: event.target.value })}
              onKeyDown={(event) => { if (event.key === 'Enter' && !props.searching) props.onSearch() }}
              maxLength={100}
              placeholder={t('ws.records.calls.filter.keywordPlaceholder', locale)}
              className={`${controlClass} w-full pl-8`}
            />
          </div>
        </div>
        <button type="button" onClick={props.onSearch} disabled={props.searching} className="inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-3 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          {props.searching ? <IconLoader2 size={15} className="animate-spin" /> : <IconSearch size={15} />}{t('ws.records.calls.filter.search', locale)}
        </button>
        <button type="button" onClick={props.onReset} className="h-9 rounded-md px-2.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground">
          {t('ws.records.calls.filter.reset', locale)}
        </button>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" aria-expanded={expanded} onClick={() => props.onExpandedChange(!expanded)} className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm hover:bg-muted">
          <IconAdjustmentsHorizontal size={15} />
          {t('ws.records.calls.filter.more', locale)}{props.moreFilterCount > 0 ? ` (${props.moreFilterCount})` : ''}
          {expanded ? <IconChevronUp size={14} /> : <IconChevronDown size={14} />}
        </button>
        <div className="ml-auto flex items-center gap-2">
          {props.canExport && (
            <button type="button" onClick={props.onExport} disabled={props.exporting} className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm hover:bg-muted disabled:opacity-50">
              {props.exporting ? <IconLoader2 size={15} className="animate-spin" /> : <IconDownload size={15} />}
              {t('ws.records.calls.filter.export', locale)}
            </button>
          )}
          <button
            type="button"
            onClick={props.onColumns}
            className={cn(
              'inline-flex h-9 items-center gap-1.5 rounded-md border px-3 text-sm transition-colors',
              props.hasColumnOverride
                ? 'border-border bg-muted text-foreground hover:bg-muted/80'
                : 'border-border bg-background text-foreground hover:bg-accent',
            )}
          >
            <IconColumns3 size={16} />{t('ws.records.calls.filter.columns', locale)}
          </button>
        </div>
      </div>
      {expanded && (
        <CallRecordMoreFilters
          locale={locale} draft={draft} onChange={props.onChange}
          options={options} canFilterByOwnership={props.canFilterByOwnership}
        />
      )}
    </div>
  )
}
