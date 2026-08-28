'use client'

import type { DashboardFilter } from '@/models/custom-dashboard'
import type { UnifiedField } from '@/models/field-definition'
import { useFieldReferenceEmployeeGroups, useFieldReferenceEmployees } from '@/service/use-field-definitions'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { dashboardDatePresetRange, type DashboardDatePreset } from '@/utils/custom-dashboard'

function fieldForRef(ref: string | undefined, fields: UnifiedField[]) {
  if (!ref) return undefined
  const [source, key] = ref.split(':', 2)
  return fields.find((field) => field.source === source && field.key === key)
}

function fieldOptions(field: UnifiedField | undefined) {
  if (!field) return []
  const config = field.type_config as { options?: Array<{ value: string; label: string }> }
  return [
    ...field.options.map((option) => ({ value: option.value, label: option.label, active: option.is_active })),
    ...field.tree_nodes.map((node) => ({ value: node.value, label: node.label, active: node.is_active })),
    ...(config.options ?? []).map((option) => ({ ...option, active: true })),
  ]
}

export function WorkspaceDashboardFilters({
  filters,
  fields,
  values,
  onChange,
  timezone,
}: {
  filters: DashboardFilter[]
  fields: UnifiedField[]
  values: Record<string, unknown>
  onChange: (values: Record<string, unknown>) => void
  timezone?: string
}) {
  const { locale } = useLocaleStore()
  const employees = useFieldReferenceEmployees()
  const groups = useFieldReferenceEmployeeGroups()
  if (filters.length === 0) return null

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-xl border border-border bg-card p-4">
      {filters.map((filter) => {
        const value = values[filter.id]
        if (filter.type === 'date_range') {
          const range = value as { start?: string; end?: string } | undefined
          return <div key={filter.id} className="grid gap-1"><label className="text-xs font-medium text-muted-foreground">{filter.name}</label><div className="flex items-center gap-2"><select defaultValue="last_30_days" onChange={(event) => { if (event.target.value !== 'custom') onChange({ ...values, [filter.id]: dashboardDatePresetRange(event.target.value as DashboardDatePreset, timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone) }) }} className="h-9 rounded-lg border border-border bg-background px-2 text-sm" aria-label={t('ws.cd.datePreset', locale)}><option value="today">{t('ws.cd.preset.today', locale)}</option><option value="yesterday">{t('ws.cd.preset.yesterday', locale)}</option><option value="last_7_days">{t('ws.cd.preset.last7', locale)}</option><option value="last_30_days">{t('ws.cd.preset.last30', locale)}</option><option value="this_week">{t('ws.cd.preset.week', locale)}</option><option value="this_month">{t('ws.cd.preset.month', locale)}</option><option value="this_quarter">{t('ws.cd.preset.quarter', locale)}</option><option value="this_year">{t('ws.cd.preset.year', locale)}</option><option value="custom">{t('ws.cd.preset.custom', locale)}</option></select><input type="date" value={range?.start ?? ''} onChange={(event) => onChange({ ...values, [filter.id]: { start: event.target.value, end: range?.end ?? event.target.value } })} className="h-9 rounded-lg border border-border bg-background px-2 text-sm" aria-label={`${filter.name} ${t('ws.cd.start', locale)}`} /><span className="text-muted-foreground">–</span><input type="date" value={range?.end ?? ''} onChange={(event) => onChange({ ...values, [filter.id]: { start: range?.start ?? event.target.value, end: event.target.value } })} className="h-9 rounded-lg border border-border bg-background px-2 text-sm" aria-label={`${filter.name} ${t('ws.cd.end', locale)}`} /></div></div>
        }
        const field = fieldForRef(filter.field_key, fields)
        const options = field?.field_type === 'employee_select'
          ? (employees.data?.items ?? []).map((item) => ({ value: String(item.id), label: item.name, active: true }))
          : field?.field_type === 'group_select'
            ? (groups.data?.items ?? []).map((item) => ({ value: String(item.id), label: item.name, active: true }))
            : fieldOptions(field)
        const selected = Array.isArray(value) ? value.map(String) : value == null ? [] : [String(value)]
        return <div key={filter.id} className="grid min-w-48 gap-1"><label htmlFor={`workspace-filter-${filter.id}`} className="text-xs font-medium text-muted-foreground">{filter.name}</label><select id={`workspace-filter-${filter.id}`} multiple={filter.multiple} value={filter.multiple ? selected : selected[0] ?? ''} onChange={(event) => { const next = filter.multiple ? Array.from(event.currentTarget.selectedOptions, (option) => option.value) : event.currentTarget.value; onChange({ ...values, [filter.id]: next }) }} className="min-h-9 rounded-lg border border-border bg-background px-2 text-sm"><option value="">{t('ws.cd.unlimited', locale)}</option>{options.map((option) => <option key={option.value} value={option.value}>{option.label}{option.active ? '' : ` (${t('ws.cd.disabledOption', locale)})`}</option>)}</select></div>
      })}
    </div>
  )
}
