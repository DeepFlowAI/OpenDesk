'use client'

import { IconArrowDown, IconArrowUp, IconPlus, IconTrash } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { DashboardIcon, DASHBOARD_ICON_OPTIONS } from './dashboard-icon'
import type { DashboardFilter, DashboardSnapshotPayload } from '@/models/custom-dashboard'
import { useUnifiedFields } from '@/service/use-field-definitions'
import { DASHBOARD_MAX_FILTERS } from '@/utils/custom-dashboard'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

export type DashboardSettingsMode = 'filters' | 'basic' | 'resources' | null

const OPTION_FILTER_TYPES = new Set([
  'single_select',
  'multi_select',
  'single_select_tree',
  'multi_select_tree',
  'boolean',
  'employee_select',
  'group_select',
])

export function DashboardSettingsDrawers({
  mode,
  snapshot,
  onChange,
  onClose,
}: {
  mode: DashboardSettingsMode
  snapshot: DashboardSnapshotPayload
  onChange: (snapshot: DashboardSnapshotPayload) => void
  onClose: () => void
}) {
  const { locale } = useLocaleStore()
  const fields = useUnifiedFields({ domain: 'ticket', locale, include_metadata: true })
  const availableFields = (fields.data?.items ?? []).filter((field) => field.key && field.status === 'active')

  function updateFilter(index: number, patch: Partial<DashboardFilter>) {
    onChange({ ...snapshot, filters: snapshot.filters.map((filter, filterIndex) => filterIndex === index ? { ...filter, ...patch } : filter) })
  }

  function moveFilter(index: number, delta: number) {
    const next = [...snapshot.filters]
    const target = index + delta
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    onChange({ ...snapshot, filters: next })
  }

  function addFilter(type: 'date_range' | 'field_option') {
    const dateField = availableFields.find((field) => field.field_type === 'date' || field.field_type === 'datetime')
    const optionField = availableFields.find((field) => OPTION_FILTER_TYPES.has(field.field_type))
    const filter: DashboardFilter = type === 'date_range'
      ? { id: crypto.randomUUID(), type, name: t('cd.defaultDateFilter', locale), field_keys: dateField?.key ? [`${dateField.source}:${dateField.key}`] : ['system:created_at'], default_value: 'last_30_days' }
      : { id: crypto.randomUUID(), type, name: t('cd.defaultOptionFilter', locale), field_key: optionField?.key ? `${optionField.source}:${optionField.key}` : 'system:status', multiple: false, default_value: null }
    onChange({ ...snapshot, filters: [...snapshot.filters, filter] })
  }

  return (
    <Sheet open={mode !== null} onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent className="sm:max-w-lg">
        <SheetHeader className="border-b border-border px-6 py-5">
          <SheetTitle>{mode === 'filters' ? t('cd.filters', locale) : mode === 'basic' ? t('cd.basicSettings', locale) : t('cd.resources', locale)}</SheetTitle>
          <SheetDescription>{mode === 'filters' ? t('cd.filtersHint', locale) : mode === 'basic' ? t('cd.basicHint', locale) : t('cd.resourcesHint', locale)}</SheetDescription>
        </SheetHeader>

        {mode === 'basic' && (
          <div className="space-y-5 overflow-y-auto px-6 py-5">
            <div className="grid gap-2"><Label htmlFor="settings-dashboard-name">{t('cd.name', locale)}</Label><Input id="settings-dashboard-name" value={snapshot.name} maxLength={80} onChange={(event) => onChange({ ...snapshot, name: event.target.value })} /></div>
            <fieldset className="grid gap-2"><legend className="text-sm font-medium">{t('cd.icon', locale)}</legend><div className="flex gap-2">{DASHBOARD_ICON_OPTIONS.map((icon) => <Button key={icon} variant={snapshot.icon === icon ? 'secondary' : 'outline'} size="icon-lg" onClick={() => onChange({ ...snapshot, icon })} aria-label={icon}><DashboardIcon name={icon} /></Button>)}</div></fieldset>
            <div className="grid gap-2"><div className="flex justify-between"><Label htmlFor="settings-dashboard-description">{t('cd.description', locale)}</Label><span className="text-xs text-muted-foreground">{snapshot.description?.length ?? 0}/300</span></div><Textarea id="settings-dashboard-description" value={snapshot.description ?? ''} maxLength={300} rows={5} onChange={(event) => onChange({ ...snapshot, description: event.target.value || null })} /></div>
          </div>
        )}

        {mode === 'filters' && (
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
            <div className="mb-4 flex gap-2"><Button variant="outline" onClick={() => addFilter('date_range')} disabled={snapshot.filters.length >= DASHBOARD_MAX_FILTERS}><IconPlus />{t('cd.addDateFilter', locale)}</Button><Button variant="outline" onClick={() => addFilter('field_option')} disabled={snapshot.filters.length >= DASHBOARD_MAX_FILTERS}><IconPlus />{t('cd.addOptionFilter', locale)}</Button></div>
            {snapshot.filters.length === 0 ? <p className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">{t('cd.noFilters', locale)}</p> : <div className="space-y-3">{snapshot.filters.map((filter, index) => (
              <div key={filter.id} className="space-y-3 rounded-lg border border-border p-4">
                <div className="flex items-center gap-2"><span className="flex-1 text-xs font-medium text-muted-foreground">{filter.type === 'date_range' ? t('cd.dateFilter', locale) : t('cd.optionFilter', locale)}</span><Button variant="ghost" size="icon-xs" onClick={() => moveFilter(index, -1)} disabled={index === 0} aria-label={t('cd.moveUp', locale)}><IconArrowUp /></Button><Button variant="ghost" size="icon-xs" onClick={() => moveFilter(index, 1)} disabled={index === snapshot.filters.length - 1} aria-label={t('cd.moveDown', locale)}><IconArrowDown /></Button><Button variant="ghost" size="icon-xs" onClick={() => onChange({ ...snapshot, filters: snapshot.filters.filter((item) => item.id !== filter.id) })} aria-label={t('cd.delete', locale)}><IconTrash className="text-destructive" /></Button></div>
                <div className="grid gap-2"><Label htmlFor={`filter-name-${filter.id}`}>{t('cd.filterName', locale)}</Label><Input id={`filter-name-${filter.id}`} value={filter.name} maxLength={80} onChange={(event) => updateFilter(index, { name: event.target.value })} /></div>
                <div className="grid gap-2"><Label htmlFor={`filter-field-${filter.id}`}>{t('cd.boundField', locale)}</Label><select id={`filter-field-${filter.id}`} className="h-9 rounded-lg border border-border bg-background px-2 text-sm" value={filter.type === 'date_range' ? filter.field_keys?.[0] ?? '' : filter.field_key ?? ''} onChange={(event) => updateFilter(index, filter.type === 'date_range' ? { field_keys: event.target.value ? [event.target.value] : [] } : { field_key: event.target.value })}><option value="">{t('cd.selectField', locale)}</option>{availableFields.filter((field) => filter.type === 'date_range' ? field.field_type === 'date' || field.field_type === 'datetime' : OPTION_FILTER_TYPES.has(field.field_type)).map((field) => { const key = `${field.source}:${field.key}`; return <option key={key} value={key}>{field.name} · {key}</option> })}</select></div>
                {filter.type === 'field_option' && <div className="flex items-center justify-between"><Label htmlFor={`filter-multiple-${filter.id}`}>{t('cd.multiple', locale)}</Label><Switch id={`filter-multiple-${filter.id}`} checked={filter.multiple ?? false} onCheckedChange={(multiple) => updateFilter(index, { multiple })} /></div>}
              </div>
            ))}</div>}
          </div>
        )}

        {mode === 'resources' && (
          <div className="space-y-5 overflow-y-auto px-6 py-5">
            <UsageRow label={t('cd.usage.components', locale)} value={`${snapshot.components.length} / 20`} />
            <UsageRow label={t('cd.usage.filters', locale)} value={`${snapshot.filters.length} / 8`} />
            <UsageRow label={t('cd.usage.code', locale)} value="64 KB" />
            <UsageRow label={t('cd.usage.runtime', locale)} value="8 s" />
            <UsageRow label={t('cd.usage.queries', locale)} value="8" />
            <p className="rounded-lg bg-muted p-4 text-sm text-muted-foreground">{t('cd.resourceIsolation', locale)}</p>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

function UsageRow({ label, value }: { label: string; value: string }) {
  return <div className="flex items-center justify-between border-b border-border pb-3 text-sm"><span className="text-muted-foreground">{label}</span><span className="font-mono font-medium">{value}</span></div>
}
