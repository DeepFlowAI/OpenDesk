'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft, IconPlus, IconTrash, IconChevronDown } from '@tabler/icons-react'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { Switch } from '@/components/ui/switch'
import type { SessionRoutingCondition, SessionConditionType } from '@/models/session-routing-rule'
import { useServiceHours } from '@/service/use-service-hours'
import { useEmployeeGroups } from '@/service/use-employee-groups'
import {
  useSessionRoutingRule,
  useCreateSessionRoutingRule,
  useUpdateSessionRoutingRule,
} from '@/service/use-session-routing-rules'
import { useChannels } from '@/service/use-channels'
import type { Channel } from '@/models/channel'

type RowState = {
  _key: string
  condition_type: SessionConditionType
  operator: string
  value: string | string[]
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
  targetGroupId: number | '',
  conditions: Array<{ condition_type: SessionConditionType; operator: string; value: unknown }>
): string {
  return JSON.stringify({
    name: name.trim(),
    enabled,
    target: targetGroupId === '' ? '' : Number(targetGroupId),
    conditions: conditions.map((c) => ({
      condition_type: c.condition_type,
      operator: c.operator,
      value: normalizeConditionValue(c.condition_type, c.operator, c.value),
    })),
  })
}

const EMPTY_NEW_ROUTING_SNAPSHOT = serializeRoutingComparePayload('', true, '', [])

function defaultRow(): RowState {
  return { _key: newKey(), condition_type: 'channel', operator: 'eq', value: '' }
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

type SessionRoutingFormProps = { ruleId?: number }

export function SessionRoutingForm({ ruleId }: SessionRoutingFormProps) {
  const isNew = ruleId == null
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data: rule, isLoading: loadingRule } = useSessionRoutingRule(ruleId ?? 0)
  const { data: groupsData } = useEmployeeGroups({ page: 1, per_page: 200 })
  const { data: serviceHoursList } = useServiceHours()
  const { data: channelsData } = useChannels()
  const createMut = useCreateSessionRoutingRule()
  const updateMut = useUpdateSessionRoutingRule()

  const groups = groupsData?.items ?? []

  const sdkChannelOptions = useMemo(() => {
    const list = (channelsData ?? []) as Channel[]
    return [...list].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))
  }, [channelsData])

  const [name, setName] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [targetGroupId, setTargetGroupId] = useState<number | ''>('')
  const [rows, setRows] = useState<RowState[]>([])
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    if (isNew) {
      if (!initialized) {
        setRows([])
        setInitialized(true)
      }
      return
    }
    if (!rule || initialized) return
    setName(rule.name)
    setEnabled(rule.enabled)
    setTargetGroupId(rule.target_group_id)
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
      setSavedSnapshot(
        serializeRoutingComparePayload(
          rule.name,
          rule.enabled,
          rule.target_group_id,
          rule.conditions ?? []
        )
      )
    }
  }, [isNew, rule, initialized])

  const payloadForCompare = useMemo(
    () =>
      serializeRoutingComparePayload(name, enabled, targetGroupId, rows.map(({ _key: _, ...c }) => c)),
    [name, enabled, targetGroupId, rows]
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
    if (targetGroupId === '') {
      showToast('error', t('sr.form.validation.group', locale))
      return
    }
    const conditions: SessionRoutingCondition[] = rows.map(({ _key: _, ...c }) => c)
    const body = { name: tn, enabled, conditions, target_group_id: Number(targetGroupId) }
    try {
      if (isNew) {
        await createMut.mutateAsync(body)
        showToast('success', t('sr.form.saveSuccess', locale))
        router.push('/session-routing')
      } else if (ruleId != null) {
        await updateMut.mutateAsync({ id: ruleId, data: body })
        showToast('success', t('sr.form.saveSuccess', locale))
        setSavedSnapshot(
          serializeRoutingComparePayload(tn, enabled, Number(targetGroupId), conditions)
        )
      }
    } catch {
      showToast('error', t('sr.form.saveFailed', locale))
    }
  }

  const saveDisabled = createMut.isPending || updateMut.isPending || !isDirty || !name.trim() || targetGroupId === ''

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

        {/* Target employee group */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-0.5">
            <span className="text-sm font-medium text-foreground">{t('sr.form.targetGroup', locale)}</span>
            <span className="text-sm font-medium text-destructive">*</span>
          </div>
          <div className="relative">
            <select
              value={targetGroupId === '' ? '' : String(targetGroupId)}
              onChange={(e) => setTargetGroupId(e.target.value ? Number(e.target.value) : '')}
              className="h-10 w-full appearance-none rounded-lg border border-border bg-white px-3.5 pr-9 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="" className="text-muted-foreground">
                {t('sr.form.targetGroup.placeholder', locale)}
              </option>
              {groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
            <IconChevronDown size={18} className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          </div>
        </div>
        </div>
      </div>
    </div>
  )
}
