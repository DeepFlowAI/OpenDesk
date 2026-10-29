'use client'

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { IconAlertTriangle, IconArrowLeft, IconChevronDown, IconSearch } from '@tabler/icons-react'
import { toast } from 'sonner'

import {
  ALL_CALL_DIRECTIONS,
  ALL_CALL_SOURCES,
  CALL_DIRECTION_OPTIONS,
  CALL_EVENT_GROUPS,
  CALL_SOURCE_OPTIONS,
  pick,
} from '@/app/components/features/call-center/call-event-rule-catalog'
import {
  permissionDeniedText,
  readCallEventRuleError,
} from '@/app/components/features/call-center/call-event-rule-errors'
import { CallIntegrationTabs } from '@/app/components/features/call-center/call-integration-tabs'
import { Checkbox } from '@/components/ui/checkbox'
import { useLocaleStore } from '@/context/locale-store'
import { copyPlainTextToClipboard } from '@/lib/clipboard'
import { cn } from '@/lib/utils'
import type {
  CallEventDirection,
  CallEventRuleOption,
  CallEventRulePayload,
  CallEventSource,
  CallEventType,
} from '@/models/call-event-subscription'
import {
  useCallEventRule,
  useCallEventRuleOptions,
  useCreateCallEventRule,
  useUpdateCallEventRule,
} from '@/service/use-call-event-subscriptions'

const LIST_PATH = '/call-center/integrations/event-subscriptions'

type FormState = {
  name: string
  subscriptionId: string
  eventTypes: CallEventType[]
  directions: CallEventDirection[]
  sources: CallEventSource[]
}

type FieldKey = 'name' | 'subscription' | 'directions' | 'sources' | 'events'

const FIELD_ORDER: FieldKey[] = ['name', 'subscription', 'directions', 'sources', 'events']

const DEFAULT_FORM: FormState = {
  name: '',
  subscriptionId: '',
  eventTypes: ['call.ended'],
  directions: [...ALL_CALL_DIRECTIONS],
  sources: [...ALL_CALL_SOURCES],
}

function snapshot(form: FormState): string {
  return JSON.stringify({
    ...form,
    name: form.name.trim(),
    eventTypes: [...form.eventTypes].sort(),
    directions: [...form.directions].sort(),
    sources: [...form.sources].sort(),
  })
}

function toggleValue<T>(values: T[], value: T, checked: boolean): T[] {
  if (checked) return values.includes(value) ? values : [...values, value]
  return values.filter((item) => item !== value)
}

export function CallEventRuleForm({ ruleId }: { ruleId?: string }) {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const isZh = locale === 'zh'
  const detail = useCallEventRule(ruleId ?? null)
  const options = useCallEventRuleOptions(ruleId ?? null)
  const create = useCreateCallEventRule()
  const update = useUpdateCallEventRule()
  const saving = create.isPending || update.isPending

  const [form, setForm] = useState<FormState>(DEFAULT_FORM)
  const [saved, setSaved] = useState(() => snapshot(DEFAULT_FORM))
  const [showErrors, setShowErrors] = useState(false)
  const [nameTouched, setNameTouched] = useState(false)
  const [serverErrors, setServerErrors] = useState<Partial<Record<FieldKey, string>>>({})
  const hydratedId = useRef<string | null>(null)
  const boundSubscriptionId = detail.data?.subscription.public_id ?? null

  useEffect(() => {
    if (!detail.data || hydratedId.current === detail.data.public_id) return
    const value: FormState = {
      name: detail.data.name,
      subscriptionId: detail.data.subscription.public_id,
      eventTypes: detail.data.event_types,
      directions: detail.data.directions,
      sources: detail.data.call_sources,
    }
    setForm(value)
    setSaved(snapshot(value))
    hydratedId.current = detail.data.public_id
  }, [detail.data])

  useEffect(() => {
    if (!ruleId || !detail.isError) return
    void readCallEventRuleError(detail.error).then((info) => {
      if (info.status !== 404) return
      toast.error(isZh ? '规则不存在或已被删除' : 'Rule not found')
      router.replace(LIST_PATH)
    })
  }, [detail.error, detail.isError, isZh, router, ruleId])

  const dirty = snapshot(form) !== saved
  const leaveText = isZh ? '有未保存的修改，确定离开吗？' : 'You have unsaved changes. Leave anyway?'

  useEffect(() => {
    const unload = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault()
    }
    const pop = () => {
      if (dirty && !window.confirm(leaveText)) window.history.forward()
    }
    window.addEventListener('beforeunload', unload)
    window.addEventListener('popstate', pop)
    return () => {
      window.removeEventListener('beforeunload', unload)
      window.removeEventListener('popstate', pop)
    }
  }, [dirty, leaveText])

  const confirmLeave = () => !dirty || window.confirm(leaveText)

  const errors = useMemo(() => {
    const result: Partial<Record<FieldKey, string>> = {}
    const name = form.name.trim()
    if (!name) result.name = isZh ? '请输入规则名称' : 'Enter a rule name'
    else if (name.length < 2 || name.length > 50) {
      result.name = isZh ? '规则名称需为 2 到 50 个字符' : 'Rule name must be 2 to 50 characters'
    }
    if (!form.subscriptionId) result.subscription = isZh ? '请选择订阅接口' : 'Select a subscription'
    if (!form.directions.length) result.directions = isZh ? '请至少选择一个通话方向' : 'Select at least one direction'
    if (!form.sources.length) result.sources = isZh ? '请至少选择一个通话来源' : 'Select at least one call source'
    if (!form.eventTypes.length) result.events = isZh ? '请至少选择一个事件' : 'Select at least one event'
    return result
  }, [form, isZh])

  const visibleError = (key: FieldKey) => {
    if (serverErrors[key]) return serverErrors[key]
    if (key === 'name' && (showErrors || nameTouched)) return errors.name
    return showErrors ? errors[key] : undefined
  }

  const patch = (value: Partial<FormState>, clear: FieldKey[] = []) => {
    setForm((current) => ({ ...current, ...value }))
    if (clear.length) {
      setServerErrors((current) => {
        const next = { ...current }
        for (const key of clear) delete next[key]
        return next
      })
    }
  }

  const focusField = (key: FieldKey) => {
    const element = document.getElementById(`call-event-rule-${key}`)
    element?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    if (element instanceof HTMLInputElement || element instanceof HTMLButtonElement) element.focus()
  }

  const save = async () => {
    setShowErrors(true)
    const firstError = FIELD_ORDER.find((key) => errors[key])
    if (firstError) {
      focusField(firstError)
      return
    }
    const payload: CallEventRulePayload = {
      name: form.name.trim(),
      subscription_public_id: form.subscriptionId,
      event_types: form.eventTypes,
      directions: form.directions,
      call_sources: form.sources,
    }
    try {
      if (ruleId) {
        await update.mutateAsync({ id: ruleId, data: payload })
        setSaved(snapshot(form))
        toast.success(isZh ? '规则已保存' : 'Rule saved')
        void options.refetch()
      } else {
        const result = await create.mutateAsync(payload)
        setSaved(snapshot(form))
        toast.success(isZh ? '规则已创建' : 'Rule created')
        router.replace(`${LIST_PATH}/${result.public_id}`)
      }
    } catch (error) {
      await handleSaveError(error)
    }
  }

  const handleSaveError = async (error: unknown) => {
    const info = await readCallEventRuleError(error)
    const fieldErrors: Partial<Record<FieldKey, string>> = {}
    switch (info.detailCode) {
      case 'name_taken':
        fieldErrors.name = isZh ? '规则名称已存在' : 'Rule name already exists'
        break
      case 'subscription_unavailable':
        fieldErrors.subscription = isZh ? '订阅接口不可用，请重新选择' : 'Subscription is unavailable. Choose another'
        break
      case 'subscription_disabled':
        fieldErrors.subscription = isZh
          ? '订阅接口已停用，请先启用或更换'
          : 'The subscription is disabled. Enable it or choose another'
        break
      case 'subscription_in_use':
        fieldErrors.subscription = isZh
          ? `该订阅接口已被「${info.ruleName ?? ''}」使用`
          : `This subscription is already used by "${info.ruleName ?? ''}"`
        break
      case 'rule_limit':
        toast.error(isZh ? '最多创建 10 条规则' : 'You can create up to 10 rules')
        return
    }
    const firstField = FIELD_ORDER.find((key) => fieldErrors[key])
    if (firstField) {
      setServerErrors(fieldErrors)
      if (fieldErrors.subscription) void options.refetch()
      focusField(firstField)
      return
    }
    if (info.status === 403) {
      toast.error(permissionDeniedText(isZh))
      return
    }
    if (info.status === 404) {
      toast.error(isZh ? '规则不存在或已被删除' : 'Rule not found')
      setSaved(snapshot(form))
      router.replace(LIST_PATH)
      return
    }
    const traceId = info.traceId
    toast.error(isZh ? '保存失败，请重试' : 'Failed to save. Try again', {
      description: traceId ? `Trace ID: ${traceId}` : undefined,
      action: traceId
        ? {
            label: isZh ? '复制' : 'Copy',
            onClick: () => void copyPlainTextToClipboard(traceId),
          }
        : undefined,
    })
  }

  const goBack = () => {
    if (!confirmLeave()) return
    router.push(LIST_PATH)
  }

  if (ruleId && detail.isLoading) return <FormSkeleton />
  if (ruleId && detail.isError) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16">
        <p className="text-sm text-muted-foreground">{isZh ? '加载失败，请重试' : 'Failed to load. Try again.'}</p>
        <button
          type="button"
          onClick={() => detail.refetch()}
          className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 hover:bg-accent"
        >
          {isZh ? '重试' : 'Retry'}
        </button>
      </div>
    )
  }

  const title = ruleId
    ? `${isZh ? '编辑：' : 'Edit: '}${detail.data?.name ?? ''}`
    : isZh ? '新建规则' : 'New rule'
  const allSourcesChecked = ALL_CALL_SOURCES.every((value) => form.sources.includes(value))

  return (
    <div className="-m-8 flex min-h-full flex-col">
      <div className="sticky -top-8 z-20 bg-background">
        <div className="px-8 pt-6">
          <CallIntegrationTabs onNavigate={() => confirmLeave()} />
        </div>
        <header className="mt-4 flex h-14 items-center justify-between border-y border-border px-8">
          <button
            type="button"
            onClick={goBack}
            className="flex min-w-0 items-center gap-3 transition-colors hover:opacity-80"
            aria-label={isZh ? '返回列表' : 'Back to list'}
          >
            <IconArrowLeft size={20} className="shrink-0 text-muted-foreground" />
            <h1 className="truncate text-base font-semibold text-foreground">{title}</h1>
          </button>
          <button
            type="button"
            disabled={saving}
            onClick={() => void save()}
            className="h-9 shrink-0 rounded-lg bg-primary px-5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/80 disabled:opacity-50"
          >
            {saving ? (isZh ? '保存中…' : 'Saving…') : (isZh ? '保存' : 'Save')}
          </button>
        </header>
      </div>

      <fieldset disabled={saving} className="px-8 py-6">
        <div className="max-w-3xl">
          <FormSection title={isZh ? '基本信息' : 'Basic information'}>
            <FieldLabel htmlFor="call-event-rule-name" label={isZh ? '规则名称' : 'Rule name'} required />
            <input
              id="call-event-rule-name"
              value={form.name}
              maxLength={50}
              onChange={(event) => patch({ name: event.target.value }, ['name'])}
              onBlur={() => setNameTouched(true)}
              placeholder={isZh ? '例如：CRM 通话同步' : 'e.g. CRM call sync'}
              aria-invalid={Boolean(visibleError('name'))}
              className={cn(
                'mt-1.5 h-10 w-full rounded-lg border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring',
                visibleError('name') ? 'border-destructive' : 'border-border',
              )}
            />
            <FieldError message={visibleError('name')} />
          </FormSection>

          <FormSection title={isZh ? '订阅接口' : 'Subscription'}>
            <div role="note" className="flex gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-3 text-sm leading-6 text-foreground">
              <IconAlertTriangle size={18} className="mt-0.5 shrink-0 text-warning" />
              <p>
                {isZh
                  ? '命中规则的通话事件会包含客户号码、坐席、外部业务上下文和录音下载链接。请只选择由租户超管配置的受信任接口。'
                  : 'Matching call events include customer numbers, agents, external business context, and recording download links. Only choose trusted subscriptions configured by a tenant super admin.'}
              </p>
            </div>
            <div className="mt-5">
              <FieldLabel htmlFor="call-event-rule-subscription" label={isZh ? '订阅接口' : 'Subscription'} required />
              <div className="mt-1.5">
                <SubscriptionPicker
                  isZh={isZh}
                  value={form.subscriptionId}
                  boundSubscriptionId={boundSubscriptionId}
                  options={options.data?.options ?? []}
                  canManageGlobal={options.data?.can_manage_global ?? false}
                  loading={options.isLoading}
                  failed={options.isError}
                  invalid={Boolean(visibleError('subscription'))}
                  onRetry={() => void options.refetch()}
                  onChange={(value) => patch({ subscriptionId: value }, ['subscription'])}
                />
              </div>
              <FieldError message={visibleError('subscription')} />
            </div>
          </FormSection>

          <FormSection title={isZh ? '通话范围' : 'Call scope'}>
            <fieldset id="call-event-rule-directions" tabIndex={-1}>
              <legend className="text-sm font-medium text-foreground/80">
                <span className="mr-0.5 text-destructive">*</span>{isZh ? '通话方向' : 'Direction'}
              </legend>
              <div className="mt-3 flex gap-6">
                {CALL_DIRECTION_OPTIONS.map((option) => (
                  <CheckRow
                    key={option.value}
                    label={pick(option.label, isZh)}
                    checked={form.directions.includes(option.value)}
                    onChange={(checked) => patch({ directions: toggleValue(form.directions, option.value, checked) })}
                  />
                ))}
              </div>
              <FieldError message={visibleError('directions')} />
            </fieldset>
            <fieldset id="call-event-rule-sources" tabIndex={-1} className="mt-5">
              <div className="flex items-center justify-between">
                <legend className="text-sm font-medium text-foreground/80">
                  <span className="mr-0.5 text-destructive">*</span>{isZh ? '通话来源' : 'Call source'}
                </legend>
                <button
                  type="button"
                  onClick={() => patch({ sources: allSourcesChecked ? [] : [...ALL_CALL_SOURCES] })}
                  className="text-xs text-primary hover:underline"
                >
                  {allSourcesChecked ? (isZh ? '取消全选' : 'Clear all') : (isZh ? '全选' : 'Select all')}
                </button>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-3">
                {CALL_SOURCE_OPTIONS.map((option) => (
                  <CheckRow
                    key={option.value}
                    label={pick(option.label, isZh)}
                    checked={form.sources.includes(option.value)}
                    onChange={(checked) => patch({ sources: toggleValue(form.sources, option.value, checked) })}
                  />
                ))}
              </div>
              <FieldError message={visibleError('sources')} />
            </fieldset>
          </FormSection>

          <FormSection title={isZh ? '事件' : 'Events'}>
            <div id="call-event-rule-events" tabIndex={-1} className="flex flex-col gap-4">
              {CALL_EVENT_GROUPS.map((group) => {
                const codes = group.events.map((event) => event.code)
                const allChecked = codes.every((code) => form.eventTypes.includes(code))
                return (
                  <div key={group.title.en} className="rounded-lg border border-border p-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-medium text-foreground">{pick(group.title, isZh)}</h3>
                      <button
                        type="button"
                        onClick={() => patch({
                          eventTypes: allChecked
                            ? form.eventTypes.filter((code) => !codes.includes(code))
                            : Array.from(new Set([...form.eventTypes, ...codes])),
                        })}
                        className="text-xs text-primary hover:underline"
                      >
                        {allChecked ? (isZh ? '取消本组' : 'Clear group') : (isZh ? '选择本组' : 'Select group')}
                      </button>
                    </div>
                    <div className="mt-3 flex flex-col gap-3">
                      {group.events.map((event) => (
                        <label key={event.code} className="flex cursor-pointer items-start gap-2">
                          <Checkbox
                            className="mt-0.5"
                            checked={form.eventTypes.includes(event.code)}
                            onCheckedChange={(checked) => patch({
                              eventTypes: toggleValue(form.eventTypes, event.code, Boolean(checked)),
                            })}
                          />
                          <span className="min-w-0">
                            <span className="flex flex-wrap items-baseline gap-2">
                              <span className="text-sm font-medium text-foreground">{pick(event.label, isZh)}</span>
                              <span className="font-mono text-[11px] text-muted-foreground">{event.code}</span>
                            </span>
                            <span className="mt-0.5 block text-xs text-muted-foreground">{pick(event.hint, isZh)}</span>
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                )
              })}
            </div>
            <FieldError message={visibleError('events')} />
          </FormSection>

          <FormSection title={isZh ? '录音获取' : 'Recording access'} last>
            <p className="text-sm leading-6 text-muted-foreground">
              {isZh
                ? '录音完成后，事件中会包含录音元数据和 1 小时有效的下载链接。链接过期后，接收方可用 API Key 调用录音开放接口重新获取。'
                : 'Recording events include metadata and a download link valid for 1 hour. After it expires, receivers can call the recording open API with an API key to get a new link.'}
            </p>
          </FormSection>
        </div>
      </fieldset>
    </div>
  )
}

function SubscriptionPicker({
  isZh,
  value,
  boundSubscriptionId,
  options,
  canManageGlobal,
  loading,
  failed,
  invalid,
  onRetry,
  onChange,
}: {
  isZh: boolean
  value: string
  boundSubscriptionId: string | null
  options: CallEventRuleOption[]
  canManageGlobal: boolean
  loading: boolean
  failed: boolean
  invalid: boolean
  onRetry: () => void
  onChange: (value: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const selected = options.find((option) => option.public_id === value)
  const isSelectable = (option: CallEventRuleOption) =>
    !option.used_by_rule_name && (option.is_active || option.public_id === boundSubscriptionId)
  const hasSelectable = options.some(isSelectable)
  const filtered = useMemo(() => {
    const keyword = search.trim().toLocaleLowerCase()
    return keyword ? options.filter((option) => option.name.toLocaleLowerCase().includes(keyword)) : options
  }, [options, search])

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', closeOnEscape)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', closeOnEscape)
    }
  }, [open])

  if (!loading && !failed && !hasSelectable && !value) {
    return (
      <div id="call-event-rule-subscription" className="rounded-lg border border-dashed border-border bg-muted/40 px-3 py-3 text-sm">
        <p className="text-foreground">{isZh ? '暂无可用订阅接口' : 'No available subscriptions'}</p>
        {canManageGlobal ? (
          <Link href="/event-subscriptions/new" target="_blank" rel="noreferrer" className="mt-1 inline-block text-primary hover:underline">
            {isZh ? '前往全局设置创建订阅' : 'Create one in global settings'}
          </Link>
        ) : (
          <p className="mt-1 text-muted-foreground">{isZh ? '请联系租户超管创建' : 'Contact a tenant super admin to create one'}</p>
        )}
      </div>
    )
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        id="call-event-rule-subscription"
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className={cn(
          'flex h-10 w-full items-center gap-2 rounded-lg border bg-background px-3 text-left text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring',
          invalid ? 'border-destructive' : 'border-border',
        )}
      >
        <span className={cn('min-w-0 flex-1 truncate', !selected && 'text-muted-foreground')}>
          {selected?.name ?? (isZh ? '选择订阅接口' : 'Select a subscription')}
        </span>
        {selected && !selected.is_active && <DisabledBadge isZh={isZh} />}
        <IconChevronDown size={16} className="shrink-0 text-muted-foreground" />
      </button>

      {open && (
        <div className="absolute left-0 top-11 z-30 w-full rounded-lg border border-border bg-popover p-2 shadow-lg">
          <div className="mb-2 flex h-8 items-center gap-1.5 rounded-md border border-border px-2">
            <IconSearch size={14} className="text-muted-foreground" />
            <input
              autoFocus
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={isZh ? '搜索订阅接口' : 'Search subscriptions'}
              aria-label={isZh ? '搜索订阅接口' : 'Search subscriptions'}
              className="min-w-0 flex-1 bg-transparent text-sm outline-none"
            />
          </div>
          <div role="listbox" className="max-h-60 overflow-y-auto">
            {loading ? (
              <div className="px-2 py-3 text-center text-xs text-muted-foreground">{isZh ? '加载中…' : 'Loading…'}</div>
            ) : failed ? (
              <div className="flex flex-col items-center gap-2 px-2 py-3 text-xs text-muted-foreground">
                <span>{isZh ? '订阅接口加载失败，请重试' : 'Failed to load subscriptions. Try again'}</span>
                <button type="button" onClick={onRetry} className="text-primary hover:underline">
                  {isZh ? '重试' : 'Retry'}
                </button>
              </div>
            ) : filtered.length === 0 ? (
              <div className="px-2 py-3 text-center text-xs text-muted-foreground">{isZh ? '无匹配结果' : 'No results'}</div>
            ) : filtered.map((option) => {
              const selectable = isSelectable(option)
              return (
                <button
                  key={option.public_id}
                  type="button"
                  role="option"
                  aria-selected={option.public_id === value}
                  aria-disabled={!selectable}
                  disabled={!selectable}
                  onClick={() => {
                    onChange(option.public_id)
                    setSearch('')
                    setOpen(false)
                  }}
                  className={cn(
                    'flex w-full items-center gap-2 rounded-md px-2 py-2 text-left text-sm',
                    selectable ? 'hover:bg-accent' : 'cursor-not-allowed opacity-50',
                    option.public_id === value && 'bg-accent',
                  )}
                >
                  <span className="min-w-0 flex-1 truncate text-foreground">{option.name}</span>
                  {!option.is_active && <DisabledBadge isZh={isZh} />}
                  {option.used_by_rule_name && (
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {isZh ? `已被「${option.used_by_rule_name}」使用` : `Used by "${option.used_by_rule_name}"`}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function DisabledBadge({ isZh }: { isZh: boolean }) {
  return (
    <span className="shrink-0 rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
      {isZh ? '已停用' : 'Disabled'}
    </span>
  )
}

function FormSection({ title, children, last = false }: { title: string; children: ReactNode; last?: boolean }) {
  return (
    <section className={last ? 'py-6' : 'border-b border-border py-6'}>
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  )
}

function FieldLabel({ htmlFor, label, required = false }: { htmlFor: string; label: string; required?: boolean }) {
  return (
    <label htmlFor={htmlFor} className="text-sm font-medium text-foreground/80">
      {required && <span className="mr-0.5 text-destructive">*</span>}
      {label}
    </label>
  )
}

function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p role="alert" className="mt-1.5 text-xs text-destructive">{message}</p>
}

function CheckRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (checked: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm text-foreground">
      <Checkbox checked={checked} onCheckedChange={(value) => onChange(Boolean(value))} />
      {label}
    </label>
  )
}

function FormSkeleton() {
  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div className="h-10 animate-pulse rounded bg-muted" />
      <div className="h-14 animate-pulse rounded bg-muted" />
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="h-32 animate-pulse rounded-lg bg-muted" />
      ))}
    </div>
  )
}
