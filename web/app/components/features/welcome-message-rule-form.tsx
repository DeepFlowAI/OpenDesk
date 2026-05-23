'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft, IconChevronDown, IconPlus, IconTrash } from '@tabler/icons-react'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { Switch } from '@/components/ui/switch'
import { RichTextFieldEditor } from '@/app/components/features/field-system/rich-text-field-editor'
import { useChannels } from '@/service/use-channels'
import {
  useCreateWelcomeMessageRule,
  useUpdateWelcomeMessageRule,
  useWelcomeMessageRule,
} from '@/service/use-welcome-message-rules'
import type { Channel } from '@/models/channel'
import type {
  WelcomeMessageCondition,
  WelcomeMessageConditionType,
} from '@/models/welcome-message-rule'

type RowState = {
  _key: string
  condition_type: WelcomeMessageConditionType
  operator: string
  value: string | string[]
}

function newKey() {
  return `wm-${Math.random().toString(36).slice(2, 11)}`
}

function defaultRow(): RowState {
  return { _key: newKey(), condition_type: 'channel', operator: 'eq', value: '' }
}

function operatorsForType(conditionType: WelcomeMessageConditionType): string[] {
  return conditionType === 'channel' ? ['eq', 'ne'] : ['eq', 'ne', 'any_eq', 'any_ne']
}

function isMultiSelect(operator: string): boolean {
  return operator === 'any_eq' || operator === 'any_ne'
}

function opLabel(operator: string, locale: Locale): string {
  if (operator === 'eq') return t('wm.cond.op.eq', locale)
  if (operator === 'ne') return t('wm.cond.op.ne', locale)
  if (operator === 'any_eq') return t('wm.cond.op.anyEq', locale)
  if (operator === 'any_ne') return t('wm.cond.op.anyNe', locale)
  return operator
}

function normalizeConditionValue(
  conditionType: WelcomeMessageConditionType,
  operator: string,
  value: unknown,
): string | string[] {
  if (conditionType === 'channel') {
    return value === 'web' || value === 'sdk' || value === 'websdk' ? 'websdk' : String(value ?? '')
  }
  if (isMultiSelect(operator)) {
    return Array.isArray(value) ? value.map((item) => String(item)) : []
  }
  return Array.isArray(value) ? String(value[0] ?? '') : String(value ?? '')
}

function serializeComparePayload(
  name: string,
  enabled: boolean,
  content: string,
  conditions: Array<{ condition_type: WelcomeMessageConditionType; operator: string; value: unknown }>,
): string {
  return JSON.stringify({
    name: name.trim(),
    enabled,
    content: content.trim(),
    conditions: conditions.map((condition) => ({
      condition_type: condition.condition_type,
      operator: condition.operator,
      value: normalizeConditionValue(condition.condition_type, condition.operator, condition.value),
    })),
  })
}

function stripHtml(value: string): string {
  return value.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim()
}

const EMPTY_NEW_SNAPSHOT = serializeComparePayload('', true, '', [])

type WelcomeMessageRuleFormProps = {
  ruleId?: number
}

export function WelcomeMessageRuleForm({ ruleId }: WelcomeMessageRuleFormProps) {
  const isNew = ruleId == null
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data: rule, isLoading: loadingRule } = useWelcomeMessageRule(ruleId ?? 0)
  const { data: channelsData } = useChannels()
  const createMut = useCreateWelcomeMessageRule()
  const updateMut = useUpdateWelcomeMessageRule()

  const sdkChannelOptions = useMemo(() => {
    const list = (channelsData ?? []) as Channel[]
    return [...list].sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }))
  }, [channelsData])
  const channelById = useMemo(
    () => Object.fromEntries(sdkChannelOptions.map((channel) => [String(channel.id), channel])),
    [sdkChannelOptions],
  )

  const [name, setName] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [content, setContent] = useState('')
  const [rows, setRows] = useState<RowState[]>([])
  const [initialized, setInitialized] = useState(false)
  const [savedSnapshot, setSavedSnapshot] = useState('')
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

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
    setContent(rule.content)
    setRows(
      (rule.conditions ?? []).map((condition) => ({
        _key: newKey(),
        condition_type: condition.condition_type,
        operator: condition.operator,
        value: normalizeConditionValue(condition.condition_type, condition.operator, condition.value),
      })),
    )
    setInitialized(true)
  }, [isNew, rule, initialized])

  useEffect(() => {
    if (isNew) {
      setSavedSnapshot('')
      return
    }
    if (rule && initialized) {
      setSavedSnapshot(
        serializeComparePayload(rule.name, rule.enabled, rule.content, rule.conditions ?? []),
      )
    }
  }, [isNew, rule, initialized])

  const comparePayload = useMemo(
    () => serializeComparePayload(name, enabled, content, rows.map(({ _key: _, ...condition }) => condition)),
    [name, enabled, content, rows],
  )
  const isDirty = isNew ? comparePayload !== EMPTY_NEW_SNAPSHOT : comparePayload !== savedSnapshot

  const showToast = (type: 'success' | 'error', text: string) => {
    setToast({ type, text })
    setTimeout(() => setToast(null), 3000)
  }

  const goBack = () => {
    if (isDirty && typeof window !== 'undefined' && !window.confirm(t('wm.form.leaveConfirm', locale))) {
      return
    }
    router.push('/online-service/conversation-settings')
  }

  const addRow = () => setRows((items) => [...items, defaultRow()])
  const removeRow = (key: string) => setRows((items) => items.filter((item) => item._key !== key))

  const updateRow = useCallback((key: string, patch: Partial<RowState>) => {
    setRows((items) =>
      items.map((row) => {
        if (row._key !== key) return row
        const next = { ...row, ...patch }
        if (patch.condition_type && patch.condition_type !== row.condition_type) {
          next.operator = operatorsForType(patch.condition_type)[0]
          next.value = ''
        }
        if (patch.operator && patch.operator !== row.operator) {
          const wasMulti = isMultiSelect(row.operator)
          const nowMulti = isMultiSelect(patch.operator)
          if (wasMulti !== nowMulti) next.value = nowMulti ? [] : ''
        }
        return next
      }),
    )
  }, [])

  const missingSdkValues = useMemo(() => {
    const values = new Set<string>()
    rows.forEach((row) => {
      if (row.condition_type !== 'web_sdk') return
      const rowValues = Array.isArray(row.value) ? row.value : [row.value]
      rowValues.forEach((value) => {
        const id = String(value || '')
        if (id && !channelById[id]) values.add(id)
      })
    })
    return Array.from(values)
  }, [rows, channelById])

  const validateRows = (): boolean => {
    for (const row of rows) {
      if (row.condition_type === 'channel' && !row.value) return false
      if (row.condition_type === 'web_sdk') {
        if (isMultiSelect(row.operator)) {
          if (!Array.isArray(row.value) || row.value.length === 0) return false
        } else if (!row.value || Array.isArray(row.value)) {
          return false
        }
      }
    }
    return true
  }

  const handleSave = async () => {
    const trimmedName = name.trim()
    if (!trimmedName || trimmedName.length > 64) {
      showToast('error', t('wm.form.validation.name', locale))
      return
    }
    if (!validateRows()) {
      showToast('error', t('wm.form.validation.condition', locale))
      return
    }
    if (!stripHtml(content)) {
      showToast('error', t('wm.form.validation.content', locale))
      return
    }
    if (content.length > 5000) {
      showToast('error', t('wm.form.validation.contentLength', locale))
      return
    }

    const conditions: WelcomeMessageCondition[] = rows.map(({ _key: _, ...condition }) => ({
      condition_type: condition.condition_type,
      operator: condition.operator,
      value: normalizeConditionValue(condition.condition_type, condition.operator, condition.value),
    }))
    const payload = { name: trimmedName, enabled, conditions, content }

    try {
      if (isNew) {
        const created = await createMut.mutateAsync(payload)
        showToast('success', t('wm.form.saveSuccess', locale))
        router.replace(`/online-service/conversation-settings/welcome/${created.id}`)
      } else if (ruleId != null) {
        await updateMut.mutateAsync({ id: ruleId, data: payload })
        showToast('success', t('wm.form.saveSuccess', locale))
        setSavedSnapshot(serializeComparePayload(trimmedName, enabled, content, conditions))
      }
    } catch {
      showToast('error', t('wm.form.saveFailed', locale))
    }
  }

  const saveDisabled =
    createMut.isPending ||
    updateMut.isPending ||
    !isDirty ||
    !name.trim() ||
    !stripHtml(content) ||
    !validateRows()

  if (!isNew && (loadingRule || !initialized)) {
    return <p className="p-8 text-sm text-muted-foreground">{t('wm.loading', locale)}</p>
  }
  if (!isNew && !rule && !loadingRule) {
    return <p className="p-8 text-sm text-destructive">{t('wm.notFound', locale)}</p>
  }

  const title = isNew
    ? t('wm.form.newTitle', locale)
    : t('wm.form.editTitle', locale, { name: rule?.name ?? '' })

  return (
    <div className="-m-8 flex flex-col">
      <div className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between border-b border-border bg-white px-6">
        <button type="button" onClick={goBack} className="flex items-center gap-2 text-left transition-colors">
          <IconArrowLeft size={20} className="text-muted-foreground" />
          <span className="text-base font-semibold text-foreground">{title}</span>
        </button>
        <button
          type="button"
          disabled={saveDisabled}
          onClick={handleSave}
          className="rounded-lg bg-primary px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-40"
        >
          {createMut.isPending || updateMut.isPending ? t('wm.form.saving', locale) : t('wm.form.save', locale)}
        </button>
      </div>

      {toast && (
        <div
          className={cn(
            'mx-8 mt-4 shrink-0 rounded-lg px-4 py-3 text-sm',
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700',
          )}
        >
          {toast.text}
        </div>
      )}

      <div className="flex flex-col gap-7 p-8" style={{ maxWidth: 720 }}>
        <section className="flex flex-col gap-4">
          <h2 className="text-base font-semibold text-foreground">{t('wm.form.basic', locale)}</h2>
          <div className="flex flex-col gap-2">
            <FieldLabel label={t('wm.form.name', locale)} required />
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('wm.form.name.placeholder', locale)}
              className="h-10 w-full rounded-lg border border-border bg-white px-3.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-foreground">{t('wm.form.enabled', locale)}</span>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>
        </section>

        <section className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold text-foreground">{t('wm.form.conditions', locale)}</h2>
            <p className="text-xs leading-5 text-muted-foreground">{t('wm.form.conditions.hint', locale)}</p>
          </div>

          {rows.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-border">
              {rows.map((row, index) => (
                <div
                  key={row._key}
                  className={cn(
                    'flex items-center gap-2 px-4 py-2.5',
                    index < rows.length - 1 && 'border-b border-border',
                  )}
                >
                  <SelectFrame className="w-[120px]">
                    <select
                      value={row.condition_type}
                      onChange={(event) =>
                        updateRow(row._key, { condition_type: event.target.value as WelcomeMessageConditionType })
                      }
                      className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    >
                      <option value="channel">{t('wm.cond.type.channel', locale)}</option>
                      <option value="web_sdk">{t('wm.cond.type.webSdk', locale)}</option>
                    </select>
                  </SelectFrame>

                  <SelectFrame className="w-[110px]">
                    <select
                      value={row.operator}
                      onChange={(event) => updateRow(row._key, { operator: event.target.value })}
                      className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                    >
                      {operatorsForType(row.condition_type).map((operator) => (
                        <option key={operator} value={operator}>
                          {opLabel(operator, locale)}
                        </option>
                      ))}
                    </select>
                  </SelectFrame>

                  <div className="relative min-w-0 flex-1">
                    {row.condition_type === 'channel' ? (
                      <SelectFrame>
                        <select
                          value={typeof row.value === 'string' ? row.value : ''}
                          onChange={(event) => updateRow(row._key, { value: event.target.value })}
                          className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                        >
                          <option value="">{t('wm.cond.value.channel.placeholder', locale)}</option>
                          <option value="websdk">{t('wm.cond.value.channel.webSdk', locale)}</option>
                        </select>
                      </SelectFrame>
                    ) : isMultiSelect(row.operator) ? (
                      <select
                        multiple
                        value={Array.isArray(row.value) ? row.value : []}
                        onChange={(event) => {
                          const selected = Array.from(event.target.selectedOptions, (option) => option.value)
                          updateRow(row._key, { value: selected })
                        }}
                        className="h-20 w-full rounded-lg border border-border bg-white px-2.5 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                      >
                        {sdkChannelOptions.map((channel) => (
                          <option key={channel.id} value={String(channel.id)}>
                            {channel.name}
                          </option>
                        ))}
                        {missingSdkValues.map((value) => (
                          <option key={value} value={value}>
                            {t('wm.cond.value.sdk.missing', locale, { id: value })}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <SelectFrame>
                        <select
                          value={typeof row.value === 'string' ? row.value : ''}
                          onChange={(event) => updateRow(row._key, { value: event.target.value })}
                          className="h-9 w-full appearance-none rounded-lg border border-border bg-white px-2.5 pr-7 text-[13px] text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                        >
                          <option value="">{t('wm.cond.value.sdk.placeholder', locale)}</option>
                          {sdkChannelOptions.map((channel) => (
                            <option key={channel.id} value={String(channel.id)}>
                              {channel.name}
                            </option>
                          ))}
                          {missingSdkValues.map((value) => (
                            <option key={value} value={value}>
                              {t('wm.cond.value.sdk.missing', locale, { id: value })}
                            </option>
                          ))}
                        </select>
                      </SelectFrame>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => removeRow(row._key)}
                    className="shrink-0 text-muted-foreground transition-colors hover:text-destructive"
                    aria-label={t('wm.form.deleteCondition', locale)}
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
            {t('wm.form.addCondition', locale)}
          </button>
        </section>

        <section className="flex flex-col gap-3">
          <FieldLabel label={t('wm.form.content', locale)} required />
          <RichTextFieldEditor
            value={content}
            onChange={(value) => setContent(value ?? '')}
            placeholder={t('wm.form.content.placeholder', locale)}
          />
        </section>
      </div>
    </div>
  )
}

function FieldLabel({ label, required }: { label: string; required?: boolean }) {
  return (
    <div className="flex items-center gap-0.5">
      <span className="text-sm font-medium text-foreground">{label}</span>
      {required && <span className="text-sm font-medium text-destructive">*</span>}
    </div>
  )
}

function SelectFrame({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cn('relative shrink-0', className)}>
      {children}
      <IconChevronDown
        size={14}
        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground"
      />
    </div>
  )
}
