'use client'

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { IconArrowLeft, IconChevronDown, IconPlus, IconTrash } from '@tabler/icons-react'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { Switch } from '@/components/ui/switch'
import { RichTextFieldEditor } from '@/app/components/features/field-system/rich-text-field-editor'
import { useChannels } from '@/service/use-channels'
import {
  useConversationAnnouncement,
  useCreateConversationAnnouncement,
  useUpdateConversationAnnouncement,
} from '@/service/use-conversation-announcements'
import type { Channel } from '@/models/channel'
import type {
  AnnouncementBackgroundColor,
  AnnouncementTimeRangeType,
  ConversationAnnouncementCondition,
} from '@/models/conversation-announcement'
import { ANNOUNCEMENT_BACKGROUND_VALUES } from '@/models/conversation-announcement'
import type { WelcomeMessageConditionType } from '@/models/welcome-message-rule'

type RowState = {
  _key: string
  condition_type: WelcomeMessageConditionType
  operator: string
  value: string | string[]
}

const BACKGROUND_KEYS: AnnouncementBackgroundColor[] = ['yellow', 'green', 'blue', 'pink', 'purple', 'gray']

function newKey() {
  return `ann-${Math.random().toString(36).slice(2, 11)}`
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

function stripHtml(value: string): string {
  return value.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ').trim()
}

function toDateTimeLocal(iso: string | null): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function dateTimeLocalToIso(value: string): string | null {
  if (!value.trim()) return null
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date.toISOString()
}

function serializeComparePayload(input: {
  name: string
  enabled: boolean
  timeRangeType: AnnouncementTimeRangeType
  startAt: string
  endAt: string
  autoPopup: boolean
  backgroundColor: AnnouncementBackgroundColor
  summaryHtml: string
  detailHtml: string
  conditions: Array<{ condition_type: WelcomeMessageConditionType; operator: string; value: unknown }>
}): string {
  return JSON.stringify({
    name: input.name.trim(),
    enabled: input.enabled,
    time_range_type: input.timeRangeType,
    start_at: input.timeRangeType === 'limited' ? input.startAt : '',
    end_at: input.timeRangeType === 'limited' ? input.endAt : '',
    auto_popup: input.autoPopup,
    background_color: input.backgroundColor,
    summary_html: input.summaryHtml.trim(),
    detail_html: input.detailHtml.trim(),
    conditions: input.conditions.map((condition) => ({
      condition_type: condition.condition_type,
      operator: condition.operator,
      value: normalizeConditionValue(condition.condition_type, condition.operator, condition.value),
    })),
  })
}

const EMPTY_NEW_SNAPSHOT = serializeComparePayload({
  name: '',
  enabled: true,
  timeRangeType: 'permanent',
  startAt: '',
  endAt: '',
  autoPopup: true,
  backgroundColor: 'yellow',
  summaryHtml: '',
  detailHtml: '',
  conditions: [],
})

type ConversationAnnouncementFormProps = {
  ruleId?: number
}

export function ConversationAnnouncementForm({ ruleId }: ConversationAnnouncementFormProps) {
  const isNew = ruleId == null
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data: rule, isLoading: loadingRule } = useConversationAnnouncement(ruleId ?? 0)
  const { data: channelsData } = useChannels()
  const createMut = useCreateConversationAnnouncement()
  const updateMut = useUpdateConversationAnnouncement()

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
  const [timeRangeType, setTimeRangeType] = useState<AnnouncementTimeRangeType>('permanent')
  const [startAt, setStartAt] = useState('')
  const [endAt, setEndAt] = useState('')
  const [rows, setRows] = useState<RowState[]>([])
  const [autoPopup, setAutoPopup] = useState(true)
  const [backgroundColor, setBackgroundColor] = useState<AnnouncementBackgroundColor>('yellow')
  const [summaryHtml, setSummaryHtml] = useState('')
  const [detailHtml, setDetailHtml] = useState('')
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
    setTimeRangeType(rule.time_range_type)
    setStartAt(toDateTimeLocal(rule.start_at))
    setEndAt(toDateTimeLocal(rule.end_at))
    setRows(
      (rule.conditions ?? []).map((condition) => ({
        _key: newKey(),
        condition_type: condition.condition_type,
        operator: condition.operator,
        value: normalizeConditionValue(condition.condition_type, condition.operator, condition.value),
      })),
    )
    setAutoPopup(rule.auto_popup)
    setBackgroundColor(rule.background_color)
    setSummaryHtml(rule.summary_html)
    setDetailHtml(rule.detail_html)
    setInitialized(true)
  }, [isNew, rule, initialized])

  useEffect(() => {
    if (isNew) {
      setSavedSnapshot('')
      return
    }
    if (rule && initialized) {
      setSavedSnapshot(
        serializeComparePayload({
          name: rule.name,
          enabled: rule.enabled,
          timeRangeType: rule.time_range_type,
          startAt: toDateTimeLocal(rule.start_at),
          endAt: toDateTimeLocal(rule.end_at),
          autoPopup: rule.auto_popup,
          backgroundColor: rule.background_color,
          summaryHtml: rule.summary_html,
          detailHtml: rule.detail_html,
          conditions: rule.conditions ?? [],
        }),
      )
    }
  }, [isNew, rule, initialized])

  const comparePayload = useMemo(
    () =>
      serializeComparePayload({
        name,
        enabled,
        timeRangeType,
        startAt,
        endAt,
        autoPopup,
        backgroundColor,
        summaryHtml,
        detailHtml,
        conditions: rows.map(({ _key: _, ...condition }) => condition),
      }),
    [name, enabled, timeRangeType, startAt, endAt, autoPopup, backgroundColor, summaryHtml, detailHtml, rows],
  )
  const isDirty = isNew ? comparePayload !== EMPTY_NEW_SNAPSHOT : comparePayload !== savedSnapshot

  const showToast = (type: 'success' | 'error', text: string) => {
    setToast({ type, text })
    setTimeout(() => setToast(null), 3000)
  }

  const goBack = () => {
    if (isDirty && typeof window !== 'undefined' && !window.confirm(t('ann.form.leaveConfirm', locale))) {
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

  const validateTimeRange = (): boolean => {
    if (timeRangeType === 'permanent') return true
    const start = dateTimeLocalToIso(startAt)
    const end = dateTimeLocalToIso(endAt)
    if (!start || !end) return false
    return new Date(end).getTime() > new Date(start).getTime()
  }

  const handleSave = async () => {
    const trimmedName = name.trim()
    if (!trimmedName || trimmedName.length > 64) {
      showToast('error', t('ann.form.validation.name', locale))
      return
    }
    if (!validateTimeRange()) {
      showToast('error', t('ann.form.validation.timeRange', locale))
      return
    }
    if (!validateRows()) {
      showToast('error', t('ann.form.validation.condition', locale))
      return
    }
    if (!stripHtml(summaryHtml)) {
      showToast('error', t('ann.form.validation.summary', locale))
      return
    }
    if (stripHtml(summaryHtml).length > 120) {
      showToast('error', t('ann.form.validation.summaryLength', locale))
      return
    }
    if (!stripHtml(detailHtml)) {
      showToast('error', t('ann.form.validation.detail', locale))
      return
    }

    const conditions: ConversationAnnouncementCondition[] = rows.map(({ _key: _, ...condition }) => ({
      condition_type: condition.condition_type,
      operator: condition.operator,
      value: normalizeConditionValue(condition.condition_type, condition.operator, condition.value),
    }))
    const payload = {
      name: trimmedName,
      enabled,
      time_range_type: timeRangeType,
      start_at: timeRangeType === 'limited' ? dateTimeLocalToIso(startAt) : null,
      end_at: timeRangeType === 'limited' ? dateTimeLocalToIso(endAt) : null,
      conditions,
      auto_popup: autoPopup,
      background_color: backgroundColor,
      summary_html: summaryHtml.trim(),
      detail_html: detailHtml.trim(),
    }

    try {
      if (isNew) {
        const created = await createMut.mutateAsync(payload)
        showToast('success', t('ann.form.saveSuccess', locale))
        router.replace(`/online-service/conversation-settings/announcements/${created.id}`)
      } else if (ruleId != null) {
        await updateMut.mutateAsync({ id: ruleId, data: payload })
        showToast('success', t('ann.form.saveSuccess', locale))
        setSavedSnapshot(comparePayload)
      }
    } catch {
      showToast('error', t('ann.form.saveFailed', locale))
    }
  }

  const saveDisabled =
    createMut.isPending ||
    updateMut.isPending ||
    !isDirty ||
    !name.trim() ||
    !validateTimeRange() ||
    !validateRows() ||
    !stripHtml(summaryHtml) ||
    !stripHtml(detailHtml)

  if (!isNew && (loadingRule || !initialized)) {
    return <p className="p-8 text-sm text-muted-foreground">{t('ann.loading', locale)}</p>
  }
  if (!isNew && !rule && !loadingRule) {
    return <p className="p-8 text-sm text-destructive">{t('ann.notFound', locale)}</p>
  }

  const title = isNew
    ? t('ann.form.newTitle', locale)
    : t('ann.form.editTitle', locale, { name: rule?.name ?? '' })

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
          {createMut.isPending || updateMut.isPending ? t('ann.form.saving', locale) : t('ann.form.save', locale)}
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

      <div className="flex max-w-[860px] flex-col gap-7 p-8">
        <section className="flex flex-col gap-4">
          <h2 className="text-base font-semibold text-foreground">{t('ann.form.basic', locale)}</h2>
          <div className="flex flex-col gap-2">
            <FieldLabel label={t('ann.form.name', locale)} required />
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={t('ann.form.name.placeholder', locale)}
              className="h-10 w-full rounded-lg border border-border bg-white px-3.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-foreground">{t('ann.form.enabled', locale)}</span>
              <Switch checked={enabled} onCheckedChange={setEnabled} />
            </div>
            <div className="flex items-center gap-2">
              {(['permanent', 'limited'] as const).map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setTimeRangeType(type)}
                  className={cn(
                    'h-9 rounded-lg border px-3.5 text-sm font-medium transition-colors',
                    timeRangeType === type
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border text-foreground/80 hover:bg-accent',
                  )}
                >
                  {t(`ann.form.time.${type}`, locale)}
                </button>
              ))}
            </div>
          </div>
          {timeRangeType === 'limited' && (
            <div className="grid gap-3 md:grid-cols-2">
              <div className="flex flex-col gap-2">
                <FieldLabel label={t('ann.form.startAt', locale)} required />
                <input
                  type="datetime-local"
                  value={startAt}
                  onChange={(event) => setStartAt(event.target.value)}
                  className="h-10 rounded-lg border border-border bg-white px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div className="flex flex-col gap-2">
                <FieldLabel label={t('ann.form.endAt', locale)} required />
                <input
                  type="datetime-local"
                  value={endAt}
                  onChange={(event) => setEndAt(event.target.value)}
                  className="h-10 rounded-lg border border-border bg-white px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
            </div>
          )}
        </section>

        <section className="flex flex-col gap-3">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold text-foreground">{t('ann.form.conditions', locale)}</h2>
            <p className="text-xs leading-5 text-muted-foreground">{t('ann.form.conditions.hint', locale)}</p>
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
                    aria-label={t('ann.form.deleteCondition', locale)}
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
            {t('ann.form.addCondition', locale)}
          </button>
        </section>

        <section className="flex flex-col gap-4">
          <h2 className="text-base font-semibold text-foreground">{t('ann.form.display', locale)}</h2>
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-foreground">{t('ann.form.autoPopup', locale)}</span>
            <Switch checked={autoPopup} onCheckedChange={setAutoPopup} />
          </div>
          <div className="flex flex-col gap-2">
            <FieldLabel label={t('ann.form.backgroundColor', locale)} required />
            <div className="flex flex-wrap gap-2">
              {BACKGROUND_KEYS.map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setBackgroundColor(key)}
                  className={cn(
                    'flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-medium transition-colors',
                    backgroundColor === key ? 'border-primary text-foreground' : 'border-border text-foreground/70 hover:bg-accent',
                  )}
                >
                  <span
                    className="h-4 w-4 rounded border border-black/10"
                    style={{ backgroundColor: ANNOUNCEMENT_BACKGROUND_VALUES[key] }}
                  />
                  {t(`ann.background.${key}`, locale)}
                </button>
              ))}
            </div>
          </div>
        </section>

        <section className="flex flex-col gap-5">
          <div className="flex flex-col gap-3">
            <FieldLabel label={t('ann.form.summary', locale)} required />
            <RichTextFieldEditor
              value={summaryHtml}
              onChange={(value) => setSummaryHtml(value ?? '')}
              typeConfig={{ rich_format: 'html' }}
              placeholder={t('ann.form.summary.placeholder', locale)}
              plainChrome
              className="min-h-[180px] rounded-lg border border-border bg-white [&_.ProseMirror]:min-h-[96px]"
            />
            <p className="text-xs text-muted-foreground">
              {t('ann.form.summary.count', locale, { count: stripHtml(summaryHtml).length })}
            </p>
          </div>
          <div className="flex flex-col gap-3">
            <FieldLabel label={t('ann.form.detail', locale)} required />
            <RichTextFieldEditor
              value={detailHtml}
              onChange={(value) => setDetailHtml(value ?? '')}
              typeConfig={{ rich_format: 'html' }}
              placeholder={t('ann.form.detail.placeholder', locale)}
              plainChrome
              className="min-h-[300px] rounded-lg border border-border bg-white [&_.ProseMirror]:min-h-[220px]"
            />
          </div>
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

function SelectFrame({ children, className }: { children: ReactNode; className?: string }) {
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
