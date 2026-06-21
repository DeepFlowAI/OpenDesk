'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import {
  IconArrowLeft,
  IconPlus,
  IconTrash,
  IconChevronDown,
  IconGripVertical,
  IconCheck,
  IconX,
} from '@tabler/icons-react'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { Switch } from '@/components/ui/switch'
import type {
  SessionRoutingCondition,
  SessionConditionType,
  SessionRoutingQueueSource,
  SessionRoutingQueueSourceType,
  SessionRoutingTargetStrategy,
} from '@/models/session-routing-rule'
import { useServiceHours } from '@/service/use-service-hours'
import { useEmployeeGroups, useEmployeeSelect } from '@/service/use-employee-groups'
import { useUnifiedFields } from '@/service/use-field-definitions'
import {
  useSessionRoutingRule,
  useCreateSessionRoutingRule,
  useUpdateSessionRoutingRule,
} from '@/service/use-session-routing-rules'
import { useChannels } from '@/service/use-channels'
import type { Channel } from '@/models/channel'
import { FieldDomain, FieldType } from '@/types/field-enums'

type RowState = {
  _key: string
  condition_type: SessionConditionType
  operator: string
  value: string | string[]
}

type QueueSourceRowState = {
  _key: string
  source_type: SessionRoutingQueueSourceType
  target_ids: number[]
}

type QueueTargetOption = {
  id: number
  label: string
  description?: string | null
}

function newKey() {
  return `k-${Math.random().toString(36).slice(2, 11)}`
}

/** Normalize condition values so API JSONB shapes match controlled form state for dirty detection */
function normalizeConditionValue(
  conditionType: SessionConditionType,
  operator: string,
  value: unknown
): string | string[] {
  if (conditionType === 'channel') {
    return value === 'web' || value === 'sdk' || value === 'websdk' ? 'websdk' : String(value ?? '')
  }
  if (conditionType === 'web_sdk' && (operator === 'any_eq' || operator === 'any_ne')) {
    if (!Array.isArray(value)) return []
    return value.map((v) => String(v))
  }
  if (Array.isArray(value)) {
    return value.map((v) => String(v))
  }
  return String(value ?? '')
}

function serializeRoutingComparePayload(
  name: string,
  enabled: boolean,
  targetStrategy: SessionRoutingTargetStrategy,
  targetSources: SessionRoutingQueueSource[],
  conditions: Array<{ condition_type: SessionConditionType; operator: string; value: unknown }>
): string {
  return JSON.stringify({
    name: name.trim(),
    enabled,
    target_strategy: targetStrategy,
    target_queue_sources: targetSources.map((source) => ({
      source_type: source.source_type,
      target_ids: source.target_ids.map((id) => Number(id)),
    })),
    conditions: conditions.map((c) => ({
      condition_type: c.condition_type,
      operator: c.operator,
      value: normalizeConditionValue(c.condition_type, c.operator, c.value),
    })),
  })
}

const EMPTY_NEW_ROUTING_SNAPSHOT = serializeRoutingComparePayload(
  '',
  true,
  'sequential_overflow',
  [{ source_type: 'employee_group', target_ids: [] }],
  []
)

function defaultRow(): RowState {
  return { _key: newKey(), condition_type: 'channel', operator: 'eq', value: '' }
}

function defaultQueueSourceRow(): QueueSourceRowState {
  return { _key: newKey(), source_type: 'employee_group', target_ids: [] }
}

function operatorsForType(ct: SessionConditionType): string[] {
  if (ct === 'channel') return ['eq', 'ne']
  if (ct === 'web_sdk') return ['eq', 'ne', 'any_eq', 'any_ne']
  return ['in_schedule', 'not_in_schedule']
}

function opLabel(op: string, locale: Locale): string {
  if (op === 'eq') return t('sr.cond.op.eq', locale)
  if (op === 'ne') return t('sr.cond.op.ne', locale)
  if (op === 'any_eq') return t('sr.cond.op.anyEq', locale)
  if (op === 'any_ne') return t('sr.cond.op.anyNe', locale)
  if (op === 'in_schedule') return t('sr.cond.op.in', locale)
  if (op === 'not_in_schedule') return t('sr.cond.op.notIn', locale)
  return op
}

function isMultiSelect(op: string): boolean {
  return op === 'any_eq' || op === 'any_ne'
}

function channelRoutingLabel(ch: Channel): string {
  return ch.name
}

function strategyLabel(strategy: SessionRoutingTargetStrategy, locale: Locale): string {
  if (strategy === 'least_waiting_count') return t('sr.target.strategy.leastWaiting', locale)
  if (strategy === 'shortest_tail_wait') return t('sr.target.strategy.shortestTail', locale)
  return t('sr.target.strategy.sequential', locale)
}

function queueSourceTypeLabel(sourceType: SessionRoutingQueueSourceType, locale: Locale): string {
  if (sourceType === 'user_field') return t('sr.target.source.userField', locale)
  if (sourceType === 'employee') return t('sr.target.source.employee', locale)
  return t('sr.target.source.employeeGroup', locale)
}

function QueueTargetMultiSelect({
  value,
  options,
  onChange,
  placeholder,
  searchPlaceholder,
  emptyText,
  className,
}: {
  value: number[]
  options: QueueTargetOption[]
  onChange: (value: number[]) => void
  placeholder: string
  searchPlaceholder: string
  emptyText: string
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')

  const selectedIds = useMemo(
    () => value.map((id) => Number(id)).filter((id) => Number.isFinite(id) && id > 0),
    [value]
  )
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])
  const optionMap = useMemo(() => new Map(options.map((option) => [option.id, option])), [options])
  const selectedLabel = useMemo(
    () => selectedIds.map((id) => optionMap.get(id)?.label ?? `#${id}`).join(', '),
    [selectedIds, optionMap]
  )
  const filteredOptions = useMemo(() => {
    const keyword = search.trim().toLocaleLowerCase()
    if (!keyword) return options
    return options.filter((option) => {
      const haystack = `${option.label} ${option.description ?? ''}`.toLocaleLowerCase()
      return haystack.includes(keyword)
    })
  }, [options, search])

  const toggleOption = (id: number) => {
    if (selectedSet.has(id)) {
      onChange(selectedIds.filter((selectedId) => selectedId !== id))
      return
    }
    onChange([...selectedIds, id])
  }

  return (
    <div
      className={cn('relative', className)}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setOpen(false)
        }
      }}
    >
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex h-9 w-full items-center gap-2 rounded-lg border border-border bg-white px-2.5 text-left text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className={cn('min-w-0 flex-1 truncate', !selectedLabel && 'text-muted-foreground')}>
          {selectedLabel || placeholder}
        </span>
        {selectedIds.length > 0 && (
          <span
            onClick={(event) => {
              event.stopPropagation()
              onChange([])
              setSearch('')
            }}
            className="shrink-0 rounded text-muted-foreground transition-colors hover:text-foreground"
            aria-label="clear selection"
          >
            <IconX size={14} />
          </span>
        )}
        <IconChevronDown size={14} className="shrink-0 text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute left-0 right-0 z-50 mt-1 rounded-lg border border-border bg-white p-2 shadow-lg">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Escape') {
                setOpen(false)
              }
            }}
            placeholder={searchPlaceholder}
            className="mb-2 h-8 w-full rounded-md border border-border bg-white px-2 text-[13px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            autoFocus
          />
          <div className="max-h-56 overflow-y-auto" role="listbox" aria-multiselectable="true">
            {filteredOptions.length === 0 ? (
              <div className="px-2 py-2 text-sm text-muted-foreground">{emptyText}</div>
            ) : (
              filteredOptions.map((option) => {
                const selected = selectedSet.has(option.id)
                return (
                  <button
                    type="button"
                    key={option.id}
                    onClick={() => toggleOption(option.id)}
                    className={cn(
                      'flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-accent',
                      selected && 'bg-accent'
                    )}
                    role="option"
                    aria-selected={selected}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium text-foreground">{option.label}</span>
                      {option.description && (
                        <span className="block truncate text-xs text-muted-foreground">
                          {option.description}
                        </span>
                      )}
                    </span>
                    {selected && <IconCheck size={14} className="shrink-0 text-primary" />}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}

type SessionRoutingFormProps = { ruleId?: number }

export function SessionRoutingForm({ ruleId }: SessionRoutingFormProps) {
  const isNew = ruleId == null
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data: rule, isLoading: loadingRule } = useSessionRoutingRule(ruleId ?? 0)
  const { data: groupsData } = useEmployeeGroups({ page: 1, per_page: 200 })
  const { data: employeesData } = useEmployeeSelect({ page: 1, per_page: 200 })
  const { data: userFieldsData } = useUnifiedFields({
    domain: FieldDomain.USER,
    locale,
    include_metadata: false,
  })
  const { data: serviceHoursList } = useServiceHours()
  const { data: channelsData } = useChannels()
  const createMut = useCreateSessionRoutingRule()
  const updateMut = useUpdateSessionRoutingRule()

  const groups = groupsData?.items ?? []
  const employees = employeesData?.items ?? []
  const employeeTargetOptions = useMemo<QueueTargetOption[]>(
    () =>
      employees.map((employee) => ({
        id: employee.id,
        label: employee.display_name || employee.username,
        description: employee.display_name ? employee.username : null,
      })),
    [employees]
  )
  const groupTargetOptions = useMemo<QueueTargetOption[]>(
    () =>
      groups.map((group) => ({
        id: group.id,
        label: group.name,
        description: group.description,
      })),
    [groups]
  )
  const queueFields = useMemo(
    () =>
      (userFieldsData?.items ?? []).filter(
        (field) =>
          field.status === 'active' &&
          (field.field_type === FieldType.EMPLOYEE_SELECT || field.field_type === FieldType.GROUP_SELECT)
      ),
    [userFieldsData?.items]
  )

  const sdkChannelOptions = useMemo(() => {
    const list = (channelsData ?? []) as Channel[]
    return [...list].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))
  }, [channelsData])

  const [name, setName] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [targetStrategy, setTargetStrategy] =
    useState<SessionRoutingTargetStrategy>('sequential_overflow')
  const [queueRows, setQueueRows] = useState<QueueSourceRowState[]>([defaultQueueSourceRow()])
  const [rows, setRows] = useState<RowState[]>([])
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    if (isNew) {
      if (!initialized) {
        setRows([])
        setTargetStrategy('sequential_overflow')
        setQueueRows([defaultQueueSourceRow()])
        setInitialized(true)
      }
      return
    }
    if (!rule || initialized) return
    setName(rule.name)
    setEnabled(rule.enabled)
    setTargetStrategy(rule.target_strategy ?? 'sequential_overflow')
    const existingSources =
      rule.target_queue_sources?.length
        ? rule.target_queue_sources
        : rule.target_group_id
          ? [{ source_type: 'employee_group' as const, target_ids: [rule.target_group_id] }]
          : []
    setQueueRows(
      existingSources.length
        ? existingSources.map((source) => ({ _key: newKey(), ...source }))
        : [defaultQueueSourceRow()]
    )
    setRows(
      (rule.conditions ?? []).map((c) => ({
        _key: newKey(),
        condition_type: c.condition_type,
        operator: c.operator,
        value: normalizeConditionValue(c.condition_type, c.operator, c.value),
      }))
    )
    setInitialized(true)
  }, [isNew, rule, initialized])

  const [savedSnapshot, setSavedSnapshot] = useState('')
  useEffect(() => {
    if (isNew) {
      setSavedSnapshot('')
      return
    }
    if (rule && initialized) {
      const existingSources =
        rule.target_queue_sources?.length
          ? rule.target_queue_sources
          : rule.target_group_id
            ? [{ source_type: 'employee_group' as const, target_ids: [rule.target_group_id] }]
            : []
      setSavedSnapshot(
        serializeRoutingComparePayload(
          rule.name,
          rule.enabled,
          rule.target_strategy ?? 'sequential_overflow',
          existingSources,
          rule.conditions ?? []
        )
      )
    }
  }, [isNew, rule, initialized])

  const normalizedQueueSources = useMemo<SessionRoutingQueueSource[]>(
    () =>
      queueRows.map(({ _key: _, source_type, target_ids }) => ({
        source_type,
        target_ids: target_ids.map((id) => Number(id)).filter((id) => Number.isFinite(id) && id > 0),
      })),
    [queueRows]
  )

  const payloadForCompare = useMemo(
    () =>
      serializeRoutingComparePayload(
        name,
        enabled,
        targetStrategy,
        normalizedQueueSources,
        rows.map(({ _key: _, ...c }) => c)
      ),
    [name, enabled, targetStrategy, normalizedQueueSources, rows]
  )

  const isDirty = isNew ? payloadForCompare !== EMPTY_NEW_ROUTING_SNAPSHOT : payloadForCompare !== savedSnapshot

  const goBack = () => {
    if (isDirty && typeof window !== 'undefined' && !window.confirm(t('sr.form.leaveConfirm', locale))) {
      return
    }
    router.push('/session-routing')
  }

  const addRow = () => setRows((r) => [...r, defaultRow()])
  const removeRow = (key: string) => setRows((r) => r.filter((x) => x._key !== key))
  const addQueueRow = () => setQueueRows((r) => [...r, defaultQueueSourceRow()])
  const removeQueueRow = (key: string) =>
    setQueueRows((r) => (r.length > 1 ? r.filter((x) => x._key !== key) : [defaultQueueSourceRow()]))
  const [dragQueueRowKey, setDragQueueRowKey] = useState<string | null>(null)

  const moveQueueRow = useCallback((fromKey: string, toKey: string) => {
    setQueueRows((current) => {
      const fromIndex = current.findIndex((row) => row._key === fromKey)
      const toIndex = current.findIndex((row) => row._key === toKey)
      if (fromIndex < 0 || toIndex < 0 || fromIndex === toIndex) return current

      const next = [...current]
      const [moved] = next.splice(fromIndex, 1)
      next.splice(toIndex, 0, moved)
      return next
    })
  }, [])

  const updateRow = useCallback((key: string, patch: Partial<RowState>) => {
    setRows((r) =>
      r.map((row) => {
        if (row._key !== key) return row
        const next = { ...row, ...patch }
        if (patch.condition_type && patch.condition_type !== row.condition_type) {
          const ops = operatorsForType(patch.condition_type)
          next.operator = ops[0]
          next.value = ''
        }
        if (patch.operator && patch.operator !== row.operator) {
          const wasMulti = isMultiSelect(row.operator)
          const nowMulti = isMultiSelect(patch.operator)
          if (wasMulti !== nowMulti) {
            next.value = nowMulti ? [] : ''
          }
        }
        return next
      })
    )
  }, [])

  const updateQueueRow = useCallback((key: string, patch: Partial<QueueSourceRowState>) => {
    setQueueRows((r) =>
      r.map((row) => {
        if (row._key !== key) return row
        const next = { ...row, ...patch }
        if (patch.source_type && patch.source_type !== row.source_type) {
          next.target_ids = []
        }
        return next
      })
    )
  }, [])

  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const showToast = (type: 'success' | 'error', text: string) => {
    setToast({ type, text })
    setTimeout(() => setToast(null), 3000)
  }

  const handleSave = async () => {
    const tn = name.trim()
    if (!tn || tn.length > 64) {
      showToast('error', t('sr.form.validation.name', locale))
      return
    }
    const validSources = normalizedQueueSources.filter((source) => source.target_ids.length > 0)
    if (validSources.length === 0) {
      showToast('error', t('sr.form.validation.queueSource', locale))
      return
    }
    const invalidSource = normalizedQueueSources.find((source) => source.target_ids.length === 0)
    if (invalidSource) {
      const key =
        invalidSource.source_type === 'employee'
          ? 'sr.form.validation.employee'
          : invalidSource.source_type === 'user_field'
            ? 'sr.form.validation.userField'
            : 'sr.form.validation.group'
      showToast('error', t(key, locale))
      return
    }
    const conditions: SessionRoutingCondition[] = rows.map(({ _key: _, ...c }) => c)
    const body = {
      name: tn,
      enabled,
      conditions,
      target_strategy: targetStrategy,
      target_queue_sources: validSources,
    }
    try {
      if (isNew) {
        await createMut.mutateAsync(body)
        showToast('success', t('sr.form.saveSuccess', locale))
        router.push('/session-routing')
      } else if (ruleId != null) {
        await updateMut.mutateAsync({ id: ruleId, data: body })
        showToast('success', t('sr.form.saveSuccess', locale))
        setSavedSnapshot(
          serializeRoutingComparePayload(tn, enabled, targetStrategy, validSources, conditions)
        )
      }
    } catch {
      showToast('error', t('sr.form.saveFailed', locale))
    }
  }

  const hasValidQueueSources = normalizedQueueSources.some((source) => source.target_ids.length > 0)
  const saveDisabled = createMut.isPending || updateMut.isPending || !isDirty || !name.trim() || !hasValidQueueSources

  if (!isNew && loadingRule) {
    return <p className="p-8 text-sm text-muted-foreground">{t('sr.loading', locale)}</p>
  }
  if (!isNew && !rule && !loadingRule) {
    return <p className="p-8 text-sm text-red-600">Not found</p>
  }

  const title = isNew
    ? t('sr.form.newTitle', locale)
    : t('sr.form.editTitle', locale, { name: rule?.name ?? '' })

  return (
    <div className="-m-8 flex flex-col">
      {/* Sticky top bar */}
      <div className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <button
          type="button"
          onClick={goBack}
          className="flex items-center gap-2 text-left transition-colors"
        >
          <IconArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold text-foreground">{title}</span>
        </button>
        <button
          type="button"
          disabled={saveDisabled}
          onClick={handleSave}
          className="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-40"
        >
          {createMut.isPending || updateMut.isPending
            ? t('sr.form.saving', locale)
            : t('sr.form.save', locale)}
        </button>
      </div>

      {toast && (
        <div
          className={cn(
            'mx-8 mt-4 shrink-0 rounded-lg px-4 py-3 text-sm',
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          )}
        >
          {toast.text}
        </div>
      )}

      {/* Form content — max-width 720 per design */}
      <div>
        <div className="flex flex-col gap-6 p-8" style={{ maxWidth: 720 }}>
        {/* Rule name */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-0.5">
            <span className="text-sm font-medium text-foreground">{t('sr.form.name', locale)}</span>
            <span className="text-sm font-medium text-destructive">*</span>
          </div>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t('sr.form.name.placeholder', locale)}
            className="h-10 w-full rounded-lg border border-border bg-white px-3.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        {/* Enabled toggle */}
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-foreground">{t('sr.form.enabled', locale)}</span>
          <Switch checked={enabled} onCheckedChange={setEnabled} />
        </div>

        {/* Conditions section */}
        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium text-foreground">{t('sr.form.conditions', locale)}</span>
          <p className="text-xs text-muted-foreground">{t('sr.form.conditions.hint', locale)}</p>

          {rows.length > 0 && (
            <div className="mt-1 overflow-hidden rounded-lg border border-border">
              {rows.map((row, idx) => (
                <div
                  key={row._key}
                  className={cn(
                    'flex items-center gap-2 px-4 py-2.5',
                    idx < rows.length - 1 && 'border-b border-border'
                  )}
                >
                  {/* Condition type */}
                  <div className="relative w-[120px] shrink-0">
                    <select
                      value={row.condition_type}
                      onChange={(e) =>
                        updateRow(row._key, { condition_type: e.target.value as SessionConditionType })
                      }
                      className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    >
                      <option value="channel">{t('sr.cond.type.channel', locale)}</option>
                      <option value="web_sdk">{t('sr.cond.type.webSdk', locale)}</option>
                      <option value="current_time">{t('sr.cond.type.time', locale)}</option>
                    </select>
                    <IconChevronDown size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  </div>

                  {/* Operator */}
                  <div className="relative w-[110px] shrink-0">
                    <select
                      value={row.operator}
                      onChange={(e) => updateRow(row._key, { operator: e.target.value })}
                      className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    >
                      {operatorsForType(row.condition_type).map((op) => (
                        <option key={op} value={op}>
                          {opLabel(op, locale)}
                        </option>
                      ))}
                    </select>
                    <IconChevronDown size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                  </div>

                  {/* Value */}
                  <div className="relative min-w-0 flex-1">
                    {row.condition_type === 'channel' ? (
                      <>
                        <select
                          value={typeof row.value === 'string' ? row.value : ''}
                          onChange={(e) => updateRow(row._key, { value: e.target.value })}
                          className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                        >
                          <option value="">{t('sr.cond.value.channel.placeholder', locale)}</option>
                          <option value="websdk">{t('sr.cond.value.channel.webSdk', locale)}</option>
                        </select>
                        <IconChevronDown size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                      </>
                    ) : row.condition_type === 'web_sdk' ? (
                      isMultiSelect(row.operator) ? (
                        <>
                          <select
                            multiple
                            value={Array.isArray(row.value) ? row.value : []}
                            onChange={(e) => {
                              const selected = Array.from(e.target.selectedOptions, (o) => o.value)
                              updateRow(row._key, { value: selected })
                            }}
                            className="h-20 w-full rounded-lg border border-border bg-white px-2.5 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                          >
                            {sdkChannelOptions.map((ch) => (
                              <option key={ch.id} value={String(ch.id)}>
                                {channelRoutingLabel(ch)}
                              </option>
                            ))}
                          </select>
                        </>
                      ) : (
                        <>
                          <select
                            value={typeof row.value === 'string' ? row.value : ''}
                            onChange={(e) => updateRow(row._key, { value: e.target.value })}
                            className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                          >
                            <option value="">{t('sr.cond.value.sdk.placeholder', locale)}</option>
                            {sdkChannelOptions.map((ch) => (
                              <option key={ch.id} value={String(ch.id)}>
                                {channelRoutingLabel(ch)}
                              </option>
                            ))}
                          </select>
                          <IconChevronDown size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                        </>
                      )
                    ) : (
                      <>
                        <select
                          value={typeof row.value === 'string' ? row.value : ''}
                          onChange={(e) => updateRow(row._key, { value: e.target.value })}
                          className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                        >
                          <option value="">{t('sr.cond.value.schedule.placeholder', locale)}</option>
                          {(serviceHoursList ?? []).map((sh) => (
                            <option key={sh.id} value={String(sh.id)}>
                              {sh.name}
                            </option>
                          ))}
                        </select>
                        <IconChevronDown size={14} className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground" />
                      </>
                    )}
                  </div>

                  {/* Delete */}
                  <button
                    type="button"
                    onClick={() => removeRow(row._key)}
                    className="shrink-0 text-muted-foreground transition-colors hover:text-red-600"
                    aria-label="delete condition"
                  >
                    <IconTrash size={16} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <button
            type="button"
            onClick={addRow}
            className="inline-flex h-9 w-fit items-center gap-1.5 rounded-lg border border-border px-3.5 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
          >
            <IconPlus size={16} />
            {t('sr.form.addCondition', locale)}
          </button>
        </div>

        {/* Assignment target */}
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-0.5">
            <span className="text-sm font-medium text-foreground">{t('sr.target.title', locale)}</span>
            <span className="text-sm font-medium text-destructive">*</span>
          </div>
          <div className="flex flex-col gap-2">
            <span className="text-xs font-medium text-muted-foreground">{t('sr.target.strategy', locale)}</span>
            <div className="relative">
              <select
                value={targetStrategy}
                onChange={(e) => setTargetStrategy(e.target.value as SessionRoutingTargetStrategy)}
                className="h-10 w-full appearance-none rounded-lg border border-border bg-white px-3.5 pr-9 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              >
                {(['sequential_overflow', 'least_waiting_count', 'shortest_tail_wait'] as const).map((strategy) => (
                  <option key={strategy} value={strategy}>
                    {strategyLabel(strategy, locale)}
                  </option>
                ))}
              </select>
              <IconChevronDown size={18} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            </div>
            <p className="text-xs text-muted-foreground">
              {targetStrategy === 'sequential_overflow'
                ? t('sr.target.strategy.sequentialHint', locale)
                : t('sr.target.strategy.balanceHint', locale)}
            </p>
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-xs font-medium text-muted-foreground">{t('sr.target.sources', locale)}</span>
            <div className="rounded-lg border border-border">
              {queueRows.map((row, idx) => (
                <div
                  key={row._key}
                  className={cn(
                    'flex items-start gap-2 px-4 py-2.5',
                    dragQueueRowKey === row._key && 'bg-accent/60',
                    idx < queueRows.length - 1 && 'border-b border-border'
                  )}
                  onDragOver={(event) => {
                    if (!dragQueueRowKey || dragQueueRowKey === row._key) return
                    event.preventDefault()
                    event.dataTransfer.dropEffect = 'move'
                  }}
                  onDrop={(event) => {
                    event.preventDefault()
                    if (!dragQueueRowKey) return
                    moveQueueRow(dragQueueRowKey, row._key)
                    setDragQueueRowKey(null)
                  }}
                >
                  <div
                    className="flex h-9 w-6 shrink-0 cursor-grab items-center justify-center text-muted-foreground active:cursor-grabbing"
                    draggable
                    onDragStart={(event) => {
                      event.dataTransfer.effectAllowed = 'move'
                      event.dataTransfer.setData('text/plain', row._key)
                      setDragQueueRowKey(row._key)
                    }}
                    onDragEnd={() => setDragQueueRowKey(null)}
                  >
                    <IconGripVertical size={16} />
                  </div>
                  <div className="relative w-[140px] shrink-0">
                    <select
                      value={row.source_type}
                      onChange={(e) =>
                        updateQueueRow(row._key, {
                          source_type: e.target.value as SessionRoutingQueueSourceType,
                        })
                      }
                      className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    >
                      {(['user_field', 'employee', 'employee_group'] as const).map((sourceType) => (
                        <option key={sourceType} value={sourceType}>
                          {queueSourceTypeLabel(sourceType, locale)}
                        </option>
                      ))}
                    </select>
                    <IconChevronDown size={14} className="pointer-events-none absolute right-2 top-[18px] -translate-y-1/2 text-muted-foreground" />
                  </div>

                  <div className="relative min-w-0 flex-1">
                    {row.source_type === 'user_field' ? (
                      <>
                        <select
                          value={row.target_ids[0] ? String(row.target_ids[0]) : ''}
                          onChange={(e) =>
                            updateQueueRow(row._key, {
                              target_ids: e.target.value ? [Number(e.target.value)] : [],
                            })
                          }
                          className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                        >
                          <option value="">{t('sr.target.placeholder.userField', locale)}</option>
                          {queueFields
                            .filter((field) => field.id != null)
                            .map((field) => (
                              <option key={field.id} value={String(field.id)}>
                                {field.name}
                              </option>
                            ))}
                        </select>
                        <IconChevronDown size={14} className="pointer-events-none absolute right-2 top-[18px] -translate-y-1/2 text-muted-foreground" />
                      </>
                    ) : row.source_type === 'employee' ? (
                      <QueueTargetMultiSelect
                        value={row.target_ids}
                        onChange={(targetIds) => updateQueueRow(row._key, { target_ids: targetIds })}
                        options={employeeTargetOptions}
                        placeholder={t('sr.target.placeholder.employee', locale)}
                        searchPlaceholder={t('sr.target.search.employee', locale)}
                        emptyText={t('sr.target.empty.employee', locale)}
                      />
                    ) : (
                      <QueueTargetMultiSelect
                        value={row.target_ids}
                        onChange={(targetIds) => updateQueueRow(row._key, { target_ids: targetIds })}
                        options={groupTargetOptions}
                        placeholder={t('sr.target.placeholder.employeeGroup', locale)}
                        searchPlaceholder={t('sr.target.search.employeeGroup', locale)}
                        emptyText={t('sr.target.empty.employeeGroup', locale)}
                      />
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => removeQueueRow(row._key)}
                    className="flex h-9 shrink-0 items-center text-muted-foreground transition-colors hover:text-red-600"
                    aria-label={t('sr.target.deleteSource', locale)}
                  >
                    <IconTrash size={16} />
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={addQueueRow}
              className="inline-flex h-9 w-fit items-center gap-1.5 rounded-lg border border-border px-3.5 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
            >
              <IconPlus size={16} />
              {t('sr.target.addSource', locale)}
            </button>
          </div>
        </div>
        </div>
      </div>
    </div>
  )
}
