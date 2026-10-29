'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  IconBrain,
  IconCheck,
  IconHeadset,
  IconPlus,
  IconTimeline,
  IconTrash,
} from '@tabler/icons-react'
import type { Locale } from '@/context/locale-store'
import {
  abandonRateLimitApiToFormPercent,
  abandonRateLimitFormToApi,
  toFiniteNumber,
} from '@/lib/auto-outbound-numbers'
import {
  DEFAULT_DAILY_TIME_WINDOWS,
  DEFAULT_RETRY_POLICY,
  type AutoOutboundAbandonPrompt,
  type AutoOutboundExecutionMode,
  type AutoOutboundPacingMode,
  type AutoOutboundRetryPolicy,
  type AutoOutboundTask,
  type CreateAutoOutboundTaskPayload,
  type DailyTimeWindow,
} from '@/models/auto-outbound-task'
import { useEmployees } from '@/service/use-employees'
import { useEmployeeGroups } from '@/service/use-employee-groups'
import { useOutboundTaskTemplates } from '@/service/use-outbound-tasks'
import { useVoiceSpeedAgents } from '@/service/use-open-agent-settings'
import { useTenantPhoneNumbers } from '@/service/use-tenant-phone-numbers'
import { useVoiceFlowsSelect } from '@/service/use-voice-flows'
import { FIELD_TYPE_LABELS, type FieldType } from '@/types/field-enums'
import { planFieldVariables } from '@/lib/outbound-field-variables'
import type { OutboundTaskField } from '@/models/outbound-task'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import { EmptyState } from '@/app/components/features/engagement/outbound-task-ui'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Switch } from '@/components/ui/switch'

export type AutoOutboundFormValues = Omit<CreateAutoOutboundTaskPayload, 'template_id'> & {
  template_id: number | null
}

type Props = {
  locale: Locale
  mode: 'create' | 'edit'
  /** Title row (back + heading); rendered above the step strip in one header. */
  header: ReactNode
  initial?: AutoOutboundTask | null
  currentUserId?: number | null
  lockExecution?: boolean
  submitting?: boolean
  onCancel: () => void
  onSaveDraft: (values: AutoOutboundFormValues) => Promise<void>
  onStart: (values: AutoOutboundFormValues) => Promise<void>
}

const MODE_CARDS: Array<{
  key: AutoOutboundExecutionMode
  icon: typeof IconTimeline
  titleKey: string
  descKey: string
}> = [
  { key: 'ivr', icon: IconTimeline, titleKey: 'ws.autoOutbound.mode.ivr', descKey: 'ws.autoOutbound.mode.ivr.desc' },
  { key: 'bot', icon: IconBrain, titleKey: 'ws.autoOutbound.mode.bot', descKey: 'ws.autoOutbound.mode.bot.desc' },
  { key: 'agent', icon: IconHeadset, titleKey: 'ws.autoOutbound.mode.agent', descKey: 'ws.autoOutbound.mode.agent.desc' },
]

function todayISO(): string {
  return new Date().toISOString().slice(0, 10)
}

function plusDaysISO(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString().slice(0, 10)
}

export function formatTaskFieldDescription(
  fieldType: FieldType,
  agentEditable: boolean,
  locale: Locale,
): string {
  const label = FIELD_TYPE_LABELS[fieldType]?.[locale === 'zh' ? 'zh' : 'en'] ?? fieldType
  return agentEditable ? `${label} · ${t('ws.autoOutbound.field.agentEditable', locale)}` : label
}

/** Read-only list of which task fields a voice bot call passes as variables. */
export function CallVariablesPreview({
  locale,
  fields,
  agentChanged,
}: {
  locale: Locale
  fields: OutboundTaskField[]
  agentChanged: boolean
}) {
  const plans = planFieldVariables(fields)
  const passed = plans.filter((plan) => plan.skipReason === null)
  const skipped = plans.filter((plan) => plan.skipReason !== null)
  const overLimit = skipped.some((plan) => plan.skipReason === 'over_limit')
  const headerClass = 'grid grid-cols-[1fr_200px] gap-3 border-b border-border bg-muted/50 px-3 py-2 text-[11px] font-medium text-muted-foreground'
  const rowClass = 'grid grid-cols-[1fr_200px] gap-3 border-b border-border px-3 py-2.5 text-sm last:border-b-0'

  return (
    <section data-testid="auto-outbound-call-variables-preview" className="grid gap-2 text-sm">
      <span className="font-medium">{t('ws.autoOutbound.callVariables.title', locale)}</span>
      <p className="text-xs text-muted-foreground">{t('ws.autoOutbound.callVariables.hint', locale)}</p>
      {overLimit && (
        <p className="text-xs text-warning">{t('ws.autoOutbound.callVariables.overLimit', locale)}</p>
      )}
      {agentChanged && (
        <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs">
          {t('ws.autoOutbound.callVariables.agentChanged', locale)}
        </div>
      )}
      {plans.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
          {t('ws.autoOutbound.callVariables.empty', locale)}
        </div>
      ) : (
        <>
          {passed.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-border">
              <div className={headerClass}>
                <span>{t('ws.autoOutbound.callVariables.passed', locale)}</span>
                <span>{t('ws.autoOutbound.callVariables.col.note', locale)}</span>
              </div>
              {passed.map((plan) => (
                <div key={plan.key} className={rowClass}>
                  <span className="break-all font-mono text-xs leading-5">{plan.name}</span>
                  <span className="text-muted-foreground">{t('ws.autoOutbound.callVariables.willPass', locale)}</span>
                </div>
              ))}
            </div>
          )}
          {skipped.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-border">
              <div className={headerClass}>
                <span>{t('ws.autoOutbound.callVariables.skipped', locale)}</span>
                <span>{t('ws.autoOutbound.callVariables.col.reason', locale)}</span>
              </div>
              {skipped.map((plan) => (
                <div key={plan.key} className={rowClass}>
                  <span className="break-all">{plan.name || '—'}</span>
                  <span className="text-muted-foreground">
                    {t(`ws.autoOutbound.callVariables.reason.${plan.skipReason}`, locale)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  )
}

function buildInitial(task?: AutoOutboundTask | null, ownerId?: number | null): AutoOutboundFormValues {
  if (task) {
    return {
      name: task.name,
      template_id: task.template_id,
      description: task.description,
      owner_id: task.owner_id,
      execution_mode: task.execution_mode,
      voice_flow_id: task.voice_flow_id,
      transfer_queue_id: task.transfer_queue_id,
      voicespeed_agent_id: task.voicespeed_agent_id,
      intent_result_field_key: task.intent_result_field_key,
      queue_id: task.queue_id,
      pacing_mode: task.pacing_mode ?? 'progressive',
      dial_ratio: task.dial_ratio ?? 2,
      // Form stores dial_intensity as-is; coerce Decimal strings from the API.
      dial_intensity: toFiniteNumber(task.dial_intensity) ?? 1.5,
      // Form stores abandon_rate_limit as percent 0–100; API uses 0–1 decimal.
      abandon_rate_limit: abandonRateLimitApiToFormPercent(task.abandon_rate_limit),
      abandon_prompt: task.abandon_prompt ?? 'play_wait',
      wrapup_seconds: task.wrapup_seconds ?? 60,
      start_date: task.start_date,
      end_date: task.end_date,
      daily_time_windows: task.daily_time_windows?.length
        ? task.daily_time_windows
        : DEFAULT_DAILY_TIME_WINDOWS,
      caller_number_id: task.caller_number_id,
      max_concurrency: task.max_concurrency ?? 10,
      retry_policy: task.retry_policy ?? DEFAULT_RETRY_POLICY,
      daily_per_number_limit: task.daily_per_number_limit ?? 3,
      auto_resume_on_target_append: task.auto_resume_on_target_append ?? false,
    }
  }
  return {
    name: '',
    template_id: 0,
    description: '',
    owner_id: ownerId ?? null,
    execution_mode: 'ivr',
    voice_flow_id: null,
    transfer_queue_id: null,
    voicespeed_agent_id: null,
    intent_result_field_key: null,
    queue_id: null,
    pacing_mode: 'progressive',
    dial_ratio: 2,
    dial_intensity: 1.5,
    abandon_rate_limit: 3,
    abandon_prompt: 'play_wait',
    wrapup_seconds: 60,
    start_date: todayISO(),
    end_date: plusDaysISO(30),
    daily_time_windows: DEFAULT_DAILY_TIME_WINDOWS,
    caller_number_id: '',
    max_concurrency: 10,
    retry_policy: DEFAULT_RETRY_POLICY,
    daily_per_number_limit: 3,
    auto_resume_on_target_append: false,
  }
}

export function AutoOutboundTaskForm({
  locale,
  mode,
  header,
  initial,
  currentUserId,
  lockExecution = false,
  submitting = false,
  onCancel,
  onSaveDraft,
  onStart,
}: Props) {
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [values, setValues] = useState<AutoOutboundFormValues>(() => buildInitial(initial, currentUserId))
  const [dirty, setDirty] = useState(false)
  const [leaveOpen, setLeaveOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [agentChanged, setAgentChanged] = useState(false)

  const { data: templates, isLoading: templatesLoading } = useOutboundTaskTemplates({ page: 1, per_page: 100 })
  const { data: employees } = useEmployees({ page: 1, per_page: 100, status: 'active' })
  const { data: voiceFlows } = useVoiceFlowsSelect()
  const { data: voiceSpeedAgents } = useVoiceSpeedAgents(values.execution_mode === 'bot' || step === 2)
  const { data: groups } = useEmployeeGroups({ page: 1, per_page: 100 })
  const { data: phoneNumbers } = useTenantPhoneNumbers({ page: 1, per_page: 100 })

  useEffect(() => {
    if (initial) setValues(buildInitial(initial, currentUserId))
  }, [initial, currentUserId])

  const selectedTemplate = useMemo(
    () => templates?.items.find((item) => item.id === values.template_id) ?? null,
    [templates?.items, values.template_id],
  )

  // Editing previews the task's own copied fields, never the template's current ones.
  const variablePreviewFields = mode === 'edit' ? initial?.fields ?? [] : selectedTemplate?.fields ?? []

  const singleSelectFields = useMemo(
    () => (selectedTemplate?.fields ?? initial?.fields ?? []).filter(
      (field) => field.enabled && field.field_type === 'single_select',
    ),
    [initial?.fields, selectedTemplate?.fields],
  )

  const outboundNumbers = useMemo(
    () => (phoneNumbers?.items ?? []).filter((item) => item.call_types.includes('outbound')),
    [phoneNumbers?.items],
  )

  const patch = (partial: Partial<AutoOutboundFormValues>) => {
    setValues((prev) => ({ ...prev, ...partial }))
    setDirty(true)
    setError(null)
  }

  const patchRetry = (key: keyof AutoOutboundRetryPolicy, field: 'max_retries' | 'interval_minutes', value: number) => {
    setValues((prev) => ({
      ...prev,
      retry_policy: {
        ...prev.retry_policy,
        [key]: { ...prev.retry_policy[key], [field]: value },
      },
    }))
    setDirty(true)
  }

  const patchWindow = (index: number, field: keyof DailyTimeWindow, value: string) => {
    setValues((prev) => {
      const next = [...prev.daily_time_windows]
      next[index] = { ...next[index], [field]: value }
      return { ...prev, daily_time_windows: next }
    })
    setDirty(true)
  }

  const validateStep = (target: 1 | 2 | 3): boolean => {
    if (target >= 1) {
      if (!values.name.trim()) {
        setError(t('ws.autoOutbound.validation.nameRequired', locale))
        setStep(1)
        return false
      }
      // Edit may keep a null template_id from older tasks; create still requires one.
      if (mode === 'create' && !values.template_id) {
        setError(t('ws.autoOutbound.validation.templateRequired', locale))
        setStep(1)
        return false
      }
    }
    if (target >= 2) {
      if (!values.execution_mode) {
        setError(t('ws.autoOutbound.validation.modeRequired', locale))
        setStep(2)
        return false
      }
      if (values.execution_mode === 'ivr' && !values.voice_flow_id) {
        setError(t('ws.autoOutbound.validation.targetRequired', locale))
        setStep(2)
        return false
      }
      if (values.execution_mode === 'bot') {
        if (voiceSpeedAgents && !voiceSpeedAgents.configured) {
          setError(t('ws.autoOutbound.validation.voiceSpeedRequired', locale))
          setStep(2)
          return false
        }
        if (!values.voicespeed_agent_id || !values.transfer_queue_id) {
          setError(t('ws.autoOutbound.validation.targetRequired', locale))
          setStep(2)
          return false
        }
      }
      if (values.execution_mode === 'agent') {
        if (!values.queue_id) {
          setError(t('ws.autoOutbound.validation.targetRequired', locale))
          setStep(2)
          return false
        }
        if (values.pacing_mode === 'ratio') {
          const ratio = values.dial_ratio ?? 0
          if (ratio < 2 || ratio > 5) {
            setError(t('ws.autoOutbound.validation.ratioRange', locale))
            setStep(2)
            return false
          }
        }
        if (values.pacing_mode === 'predictive') {
          const intensity = toFiniteNumber(values.dial_intensity) ?? 0
          if (intensity < 1 || intensity > 3) {
            setError(t('ws.autoOutbound.validation.intensityRange', locale))
            setStep(2)
            return false
          }
        }
        const wrapup = values.wrapup_seconds
        if (wrapup < 15 || wrapup > 300) {
          setError(t('ws.autoOutbound.validation.wrapupRange', locale))
          setStep(2)
          return false
        }
      }
    }
    if (target >= 3) {
      if (!values.start_date || !values.end_date || values.end_date < values.start_date) {
        setError(t('ws.autoOutbound.validation.endBeforeStart', locale))
        setStep(3)
        return false
      }
      if (!values.daily_time_windows.length) {
        setError(t('ws.autoOutbound.validation.windowsRequired', locale))
        setStep(3)
        return false
      }
      if (!values.caller_number_id) {
        setError(t('ws.autoOutbound.validation.callerUnavailable', locale))
        setStep(3)
        return false
      }
      if (values.max_concurrency < 1 || values.max_concurrency > 500) {
        setError(t('ws.autoOutbound.validation.maxConcurrencyRange', locale))
        setStep(3)
        return false
      }
      if (values.daily_per_number_limit < 1 || values.daily_per_number_limit > 10) {
        setError(t('ws.autoOutbound.validation.dailyLimitRange', locale))
        setStep(3)
        return false
      }
      for (const key of ['no_answer', 'busy', 'power_off'] as const) {
        const item = values.retry_policy[key]
        if (item.max_retries < 0 || item.max_retries > 5) {
          setError(t('ws.autoOutbound.validation.maxRetriesRange', locale))
          setStep(3)
          return false
        }
        if (item.interval_minutes < 1 || item.interval_minutes > 1440) {
          setError(t('ws.autoOutbound.validation.intervalRange', locale))
          setStep(3)
          return false
        }
      }
    }
    setError(null)
    return true
  }

  const handleCancel = () => {
    if (dirty) setLeaveOpen(true)
    else onCancel()
  }

  const payload = (): AutoOutboundFormValues => {
    const base: AutoOutboundFormValues = {
      ...values,
      name: values.name.trim(),
      description: values.description?.toString().trim() || null,
      owner_id: values.owner_id ?? null,
    }
    if (base.execution_mode === 'ivr') {
      return {
        ...base,
        transfer_queue_id: null,
        voicespeed_agent_id: null,
        intent_result_field_key: null,
        queue_id: null,
        pacing_mode: null,
        dial_ratio: null,
        dial_intensity: null,
        abandon_rate_limit: null,
        abandon_prompt: null,
      }
    }
    if (base.execution_mode === 'bot') {
      return {
        ...base,
        voice_flow_id: null,
        queue_id: null,
        pacing_mode: null,
        dial_ratio: null,
        dial_intensity: null,
        abandon_rate_limit: null,
        abandon_prompt: null,
      }
    }
    return {
      ...base,
      voice_flow_id: null,
      voicespeed_agent_id: null,
      intent_result_field_key: null,
      transfer_queue_id: null,
      pacing_mode: base.pacing_mode ?? 'progressive',
      dial_ratio: base.pacing_mode === 'ratio' ? base.dial_ratio ?? 2 : null,
      dial_intensity:
        base.pacing_mode === 'predictive' ? (toFiniteNumber(base.dial_intensity) ?? 1.5) : null,
      // Convert form percent → API decimal before submit.
      abandon_rate_limit:
        base.pacing_mode === 'predictive'
          ? (abandonRateLimitFormToApi(base.abandon_rate_limit) ?? 0.03)
          : null,
      abandon_prompt:
        base.pacing_mode === 'ratio' || base.pacing_mode === 'predictive'
          ? (base.abandon_prompt ?? 'play_wait')
          : null,
    }
  }

  if (templatesLoading) {
    return (
      <div className="flex h-full flex-col overflow-hidden">
        <header className="shrink-0 border-b border-border">{header}</header>
        <div className="p-6 text-sm text-muted-foreground">{t('ws.autoOutbound.loading', locale)}</div>
      </div>
    )
  }

  if ((templates?.items.length ?? 0) === 0 && mode === 'create') {
    return (
      <div className="flex h-full flex-col overflow-hidden">
        <header className="shrink-0 border-b border-border">{header}</header>
        <div className="p-6">
          <EmptyState
            title={t('ws.autoOutbound.noTemplate', locale)}
            action={(
              <Link
                href="/workspace/engagement/outbound-task-templates"
                className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground"
              >
                {t('ws.autoOutbound.goCreateTemplate', locale)}
              </Link>
            )}
          />
        </div>
      </div>
    )
  }

  const stepLabels = [
    t('ws.autoOutbound.step.basic', locale),
    t('ws.autoOutbound.step.mode', locale),
    t('ws.autoOutbound.step.schedule', locale),
  ]

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="shrink-0 border-b border-border">
        {header}
        <div className="flex items-center gap-2 px-6 pb-4">
          {stepLabels.map((label, index) => {
            const current = index + 1 === step
            const done = index + 1 < step
            return (
              <div key={label} className="flex items-center gap-2">
                {index > 0 && <span className="mx-2 h-px w-10 bg-border" />}
                <span
                  className={cn(
                    'grid h-6 w-6 place-items-center rounded-full text-[11px] font-semibold',
                    done && 'bg-success/15 text-success',
                    current && 'bg-primary text-primary-foreground',
                    !done && !current && 'bg-muted text-muted-foreground',
                  )}
                >
                  {done ? <IconCheck size={13} /> : index + 1}
                </span>
                <span className={cn('text-sm', current ? 'font-semibold' : 'text-muted-foreground')}>{label}</span>
              </div>
            )
          })}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto bg-muted/20 p-6">
        <div className="mx-auto max-w-3xl space-y-4">
          {error && (
            <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}

          {step === 1 && (
            <>
              <section className="rounded-lg border border-border bg-background p-5">
                <h2 className="text-base font-semibold">{t('ws.autoOutbound.step.basic', locale)}</h2>
                <div className="mt-4 grid gap-4">
                  <label className="grid gap-1.5 text-sm">
                    <span className="font-medium">
                      <span className="mr-0.5 text-destructive">*</span>
                      {t('ws.autoOutbound.field.name', locale)}
                    </span>
                    <input
                      value={values.name}
                      maxLength={80}
                      onChange={(e) => patch({ name: e.target.value })}
                      className="h-10 rounded-md border border-border bg-background px-3 outline-none"
                    />
                  </label>
                  <label className="grid gap-1.5 text-sm">
                    <span className="font-medium">
                      <span className="mr-0.5 text-destructive">*</span>
                      {t('ws.autoOutbound.field.template', locale)}
                    </span>
                    <select
                      value={values.template_id || ''}
                      disabled={lockExecution || mode === 'edit'}
                      onChange={(e) => patch({ template_id: Number(e.target.value) })}
                      className="h-10 rounded-md border border-border bg-background px-3 disabled:opacity-60"
                    >
                      <option value="">{t('ws.autoOutbound.selectPlaceholder', locale)}</option>
                      {templates?.items.map((template) => (
                        <option key={template.id} value={template.id}>{template.name}</option>
                      ))}
                    </select>
                    <span className="text-xs text-muted-foreground">{t('ws.autoOutbound.field.templateHint', locale)}</span>
                  </label>
                  <label className="grid gap-1.5 text-sm">
                    <span className="font-medium">{t('ws.autoOutbound.field.description', locale)}</span>
                    <textarea
                      value={values.description ?? ''}
                      onChange={(e) => patch({ description: e.target.value })}
                      rows={4}
                      className="rounded-md border border-border bg-background px-3 py-2 outline-none"
                    />
                  </label>
                  <label className="grid gap-1.5 text-sm">
                    <span className="font-medium">{t('ws.autoOutbound.field.owner', locale)}</span>
                    <select
                      value={values.owner_id ?? ''}
                      onChange={(e) => patch({ owner_id: e.target.value ? Number(e.target.value) : null })}
                      className="h-10 rounded-md border border-border bg-background px-3"
                    >
                      <option value="">{t('ws.autoOutbound.selectPlaceholder', locale)}</option>
                      {employees?.items.map((employee) => (
                        <option key={employee.id} value={employee.id}>{employee.name}</option>
                      ))}
                    </select>
                    <span className="text-xs text-muted-foreground">{t('ws.autoOutbound.field.ownerHint', locale)}</span>
                  </label>
                </div>
              </section>

              {(selectedTemplate || initial) && (
                <section className="rounded-lg border border-border bg-background p-5">
                  <h2 className="text-base font-semibold">{t('ws.autoOutbound.field.fieldsPreview', locale)}</h2>
                  <p className="mt-1 text-sm text-muted-foreground">{t('ws.autoOutbound.field.fieldsPreviewHint', locale)}</p>
                  <div className="mt-3 overflow-hidden rounded-lg border border-border">
                    <div className="grid grid-cols-[1fr_120px] gap-3 border-b border-border bg-muted/50 px-3 py-2 text-[11px] font-medium text-muted-foreground">
                      <span>{t('ws.autoOutbound.field.fieldName', locale)}</span>
                      <span>{t('ws.autoOutbound.field.fieldType', locale)}</span>
                    </div>
                    {(selectedTemplate?.fields ?? initial?.fields ?? []).map((field) => (
                      <div
                        key={field.key}
                        className="grid grid-cols-[1fr_120px] gap-3 border-b border-border px-3 py-2.5 text-sm last:border-b-0"
                      >
                        <span>{field.name}</span>
                        <span className="text-muted-foreground">
                          {formatTaskFieldDescription(field.field_type, field.agent_editable, locale)}
                        </span>
                      </div>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}

          {step === 2 && (
            <section className="rounded-lg border border-border bg-background p-5">
              <h2 className="text-base font-semibold">{t('ws.autoOutbound.step.mode', locale)}</h2>
              <div className="mt-4 grid gap-3 md:grid-cols-3">
                {MODE_CARDS.map((card) => {
                  const Icon = card.icon
                  const active = values.execution_mode === card.key
                  return (
                    <button
                      key={card.key}
                      type="button"
                      disabled={lockExecution}
                      onClick={() => patch({ execution_mode: card.key })}
                      className={cn(
                        'rounded-lg border p-4 text-left transition-colors disabled:opacity-60',
                        active ? 'border-primary bg-primary/5' : 'border-border hover:border-foreground/30',
                      )}
                    >
                      <Icon size={20} className={active ? 'text-primary' : 'text-muted-foreground'} />
                      <div className="mt-3 text-sm font-semibold">{t(card.titleKey, locale)}</div>
                      <p className="mt-1 text-xs text-muted-foreground">{t(card.descKey, locale)}</p>
                    </button>
                  )
                })}
              </div>

              <div className="mt-6 grid gap-4">
                {values.execution_mode === 'ivr' && (
                  <>
                    <label className="grid gap-1.5 text-sm">
                      <span className="font-medium">
                        <span className="mr-0.5 text-destructive">*</span>
                        {t('ws.autoOutbound.field.voiceFlow', locale)}
                      </span>
                      <select
                        value={values.voice_flow_id ?? ''}
                        disabled={lockExecution}
                        onChange={(e) => patch({ voice_flow_id: e.target.value ? Number(e.target.value) : null })}
                        className="h-10 rounded-md border border-border bg-background px-3 disabled:opacity-60"
                      >
                        <option value="">{t('ws.autoOutbound.selectPlaceholder', locale)}</option>
                        {voiceFlows?.items.map((flow) => (
                          <option key={flow.id} value={flow.id}>{flow.name}</option>
                        ))}
                      </select>
                    </label>
                  </>
                )}

                {values.execution_mode === 'bot' && (
                  <>
                    {voiceSpeedAgents && !voiceSpeedAgents.configured ? (
                      <div className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
                        {t('ws.autoOutbound.voiceSpeedNotConfigured', locale)}{' '}
                        <Link href="/open-agent-settings" className="font-medium underline">
                          {t('ws.autoOutbound.goConfigureVoiceSpeed', locale)}
                        </Link>
                      </div>
                    ) : null}
                    <label className="grid gap-1.5 text-sm">
                      <span className="font-medium">
                        <span className="mr-0.5 text-destructive">*</span>
                        {t('ws.autoOutbound.field.voiceSpeedAgent', locale)}
                      </span>
                      <select
                        value={values.voicespeed_agent_id ?? ''}
                        disabled={lockExecution}
                        onChange={(e) => {
                          const next = e.target.value || null
                          if (values.voicespeed_agent_id && next !== values.voicespeed_agent_id) setAgentChanged(true)
                          patch({ voicespeed_agent_id: next })
                        }}
                        className="h-10 rounded-md border border-border bg-background px-3 disabled:opacity-60"
                      >
                        <option value="">{t('ws.autoOutbound.selectPlaceholder', locale)}</option>
                        {voiceSpeedAgents?.items.map((agent) => (
                          <option key={agent.id} value={agent.id}>{agent.name}</option>
                        ))}
                      </select>
                    </label>
                    <label className="grid gap-1.5 text-sm">
                      <span className="font-medium">
                        <span className="mr-0.5 text-destructive">*</span>
                        {t('ws.autoOutbound.field.botTransferQueue', locale)}
                      </span>
                      <select
                        value={values.transfer_queue_id ?? ''}
                        disabled={lockExecution}
                        onChange={(e) => patch({ transfer_queue_id: e.target.value ? Number(e.target.value) : null })}
                        className="h-10 rounded-md border border-border bg-background px-3 disabled:opacity-60"
                      >
                        <option value="">{t('ws.autoOutbound.selectPlaceholder', locale)}</option>
                        {groups?.items.map((group) => (
                          <option key={group.id} value={group.id}>{group.name}</option>
                        ))}
                      </select>
                    </label>
                    <label className="grid gap-1.5 text-sm">
                      <span className="font-medium">{t('ws.autoOutbound.field.intentField', locale)}</span>
                      <select
                        value={values.intent_result_field_key ?? ''}
                        onChange={(e) => patch({ intent_result_field_key: e.target.value || null })}
                        className="h-10 rounded-md border border-border bg-background px-3"
                      >
                        <option value="">{t('ws.autoOutbound.field.intentNone', locale)}</option>
                        {singleSelectFields.map((field) => (
                          <option key={field.key} value={field.key}>{field.name}</option>
                        ))}
                      </select>
                      <span className="text-xs text-muted-foreground">{t('ws.autoOutbound.field.intentFieldHint', locale)}</span>
                    </label>
                    <CallVariablesPreview
                      locale={locale}
                      fields={variablePreviewFields}
                      agentChanged={agentChanged}
                    />
                  </>
                )}

                {values.execution_mode === 'agent' && (
                  <>
                    <label className="grid gap-1.5 text-sm">
                      <span className="font-medium">
                        <span className="mr-0.5 text-destructive">*</span>
                        {t('ws.autoOutbound.field.queue', locale)}
                      </span>
                      <select
                        value={values.queue_id ?? ''}
                        disabled={lockExecution}
                        onChange={(e) => patch({ queue_id: e.target.value ? Number(e.target.value) : null })}
                        className="h-10 rounded-md border border-border bg-background px-3 disabled:opacity-60"
                      >
                        <option value="">{t('ws.autoOutbound.selectPlaceholder', locale)}</option>
                        {groups?.items.map((group) => (
                          <option key={group.id} value={group.id}>{group.name}</option>
                        ))}
                      </select>
                    </label>
                    <fieldset className="grid gap-2 text-sm">
                      <legend className="font-medium">{t('ws.autoOutbound.field.pacing', locale)}</legend>
                      {(['progressive', 'ratio', 'predictive'] as AutoOutboundPacingMode[]).map((pacing) => (
                        <label key={pacing} className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="pacing"
                            checked={(values.pacing_mode ?? 'progressive') === pacing}
                            disabled={lockExecution}
                            onChange={() => patch({ pacing_mode: pacing })}
                          />
                          {t(`ws.autoOutbound.pacing.${pacing}`, locale)}
                        </label>
                      ))}
                    </fieldset>
                    {values.pacing_mode === 'ratio' && (
                      <label className="grid gap-1.5 text-sm">
                        <span className="font-medium">{t('ws.autoOutbound.field.dialRatio', locale)}</span>
                        <input
                          type="number"
                          min={2}
                          max={5}
                          value={values.dial_ratio ?? 2}
                          disabled={lockExecution}
                          onChange={(e) => patch({ dial_ratio: Number(e.target.value) })}
                          className="h-10 rounded-md border border-border bg-background px-3 disabled:opacity-60"
                        />
                      </label>
                    )}
                    {values.pacing_mode === 'predictive' && (
                      <>
                        <label className="grid gap-1.5 text-sm">
                          <span className="font-medium">{t('ws.autoOutbound.field.dialIntensity', locale)}</span>
                          <input
                            type="number"
                            min={1}
                            max={3}
                            step={0.1}
                            value={values.dial_intensity ?? 1.5}
                            disabled={lockExecution}
                            onChange={(e) => patch({ dial_intensity: Number(e.target.value) })}
                            className="h-10 rounded-md border border-border bg-background px-3 disabled:opacity-60"
                          />
                        </label>
                        <label className="grid gap-1.5 text-sm">
                          <span className="font-medium">{t('ws.autoOutbound.field.abandonRateLimit', locale)}</span>
                          <input
                            type="number"
                            min={0}
                            max={100}
                            value={values.abandon_rate_limit ?? 3}
                            disabled={lockExecution}
                            onChange={(e) => patch({ abandon_rate_limit: Number(e.target.value) })}
                            className="h-10 rounded-md border border-border bg-background px-3 disabled:opacity-60"
                          />
                        </label>
                      </>
                    )}
                    {(values.pacing_mode === 'ratio' || values.pacing_mode === 'predictive') && (
                      <fieldset className="grid gap-2 text-sm">
                        <legend className="font-medium">{t('ws.autoOutbound.field.abandonPrompt', locale)}</legend>
                        {(['play_wait', 'hangup'] as AutoOutboundAbandonPrompt[]).map((prompt) => (
                          <label key={prompt} className="flex items-center gap-2">
                            <input
                              type="radio"
                              name="abandon_prompt"
                              checked={(values.abandon_prompt ?? 'play_wait') === prompt}
                              disabled={lockExecution}
                              onChange={() => patch({ abandon_prompt: prompt })}
                            />
                            {t(`ws.autoOutbound.abandonPrompt.${prompt}`, locale)}
                          </label>
                        ))}
                      </fieldset>
                    )}
                    <label className="grid gap-1.5 text-sm">
                      <span className="font-medium">
                        <span className="mr-0.5 text-destructive">*</span>
                        {t('ws.autoOutbound.field.wrapupSeconds', locale)}
                      </span>
                      <input
                        type="number"
                        min={15}
                        max={300}
                        value={values.wrapup_seconds}
                        onChange={(e) => patch({ wrapup_seconds: Number(e.target.value) })}
                        className="h-10 rounded-md border border-border bg-background px-3"
                      />
                      <span className="text-xs text-muted-foreground">
                        {t('ws.autoOutbound.field.wrapupSecondsHint', locale)}
                      </span>
                    </label>
                  </>
                )}
              </div>
            </section>
          )}

          {step === 3 && (
            <>
              <section className="rounded-lg border border-border bg-background p-5">
                <h2 className="text-base font-semibold">{t('ws.autoOutbound.step.schedule', locale)}</h2>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <label className="grid gap-1.5 text-sm">
                    <span className="font-medium">
                      <span className="mr-0.5 text-destructive">*</span>
                      {t('ws.autoOutbound.field.startDate', locale)}
                    </span>
                    <input
                      type="date"
                      value={values.start_date}
                      onChange={(e) => patch({ start_date: e.target.value })}
                      className="h-10 rounded-md border border-border bg-background px-3"
                    />
                  </label>
                  <label className="grid gap-1.5 text-sm">
                    <span className="font-medium">
                      <span className="mr-0.5 text-destructive">*</span>
                      {t('ws.autoOutbound.field.endDate', locale)}
                    </span>
                    <input
                      type="date"
                      value={values.end_date}
                      onChange={(e) => patch({ end_date: e.target.value })}
                      className="h-10 rounded-md border border-border bg-background px-3"
                    />
                    <span className="text-xs text-muted-foreground">
                      {t('ws.autoOutbound.field.endDateHint', locale)}
                    </span>
                  </label>
                </div>
                <div className="mt-4">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-sm font-medium">
                      <span className="mr-0.5 text-destructive">*</span>
                      {t('ws.autoOutbound.field.dailyWindows', locale)}
                    </span>
                    <button
                      type="button"
                      onClick={() => patch({
                        daily_time_windows: [...values.daily_time_windows, { start: '09:00', end: '12:00' }],
                      })}
                      className="inline-flex items-center gap-1 text-sm text-primary"
                    >
                      <IconPlus size={14} />
                      {t('ws.autoOutbound.field.addWindow', locale)}
                    </button>
                  </div>
                  <div className="space-y-2">
                    {values.daily_time_windows.map((window, index) => (
                      <div key={`${window.start}-${index}`} className="flex items-center gap-2">
                        <input
                          type="time"
                          value={window.start}
                          onChange={(e) => patchWindow(index, 'start', e.target.value)}
                          className="h-10 rounded-md border border-border bg-background px-3"
                        />
                        <span className="text-muted-foreground">-</span>
                        <input
                          type="time"
                          value={window.end}
                          onChange={(e) => patchWindow(index, 'end', e.target.value)}
                          className="h-10 rounded-md border border-border bg-background px-3"
                        />
                        {values.daily_time_windows.length > 1 && (
                          <button
                            type="button"
                            onClick={() => patch({
                              daily_time_windows: values.daily_time_windows.filter((_, i) => i !== index),
                            })}
                            className="rounded-md p-2 text-muted-foreground hover:bg-muted"
                          >
                            <IconTrash size={16} />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
                <label className="mt-4 grid gap-1.5 text-sm">
                  <span className="font-medium">
                    <span className="mr-0.5 text-destructive">*</span>
                    {t('ws.autoOutbound.field.callerNumber', locale)}
                  </span>
                  <select
                    value={values.caller_number_id}
                    onChange={(e) => patch({ caller_number_id: e.target.value })}
                    className="h-10 rounded-md border border-border bg-background px-3"
                  >
                    <option value="">{t('ws.autoOutbound.selectPlaceholder', locale)}</option>
                    {outboundNumbers.map((number) => (
                      <option key={number.id} value={number.id}>{number.phone_number}</option>
                    ))}
                  </select>
                </label>
              </section>

              <section className="rounded-lg border border-border bg-background p-5">
                <h2 className="text-base font-semibold">{t('ws.autoOutbound.field.retryPolicy', locale)}</h2>
                <div className="mt-4 grid gap-4">
                  <label className="grid gap-1.5 text-sm">
                    <span className="font-medium">{t('ws.autoOutbound.field.maxConcurrency', locale)}</span>
                    <input
                      type="number"
                      min={1}
                      max={500}
                      value={values.max_concurrency}
                      onChange={(e) => patch({ max_concurrency: Number(e.target.value) })}
                      className="h-10 rounded-md border border-border bg-background px-3"
                    />
                  </label>
                  {([
                    ['no_answer', 'ws.autoOutbound.retry.no_answer'],
                    ['busy', 'ws.autoOutbound.retry.busy'],
                    ['power_off', 'ws.autoOutbound.retry.power_off'],
                  ] as const).map(([key, labelKey]) => (
                    <div key={key} className="rounded-md border border-border p-3">
                      <div className="mb-2 text-sm font-medium">{t(labelKey, locale)}</div>
                      <div className="grid gap-3 md:grid-cols-2">
                        <label className="grid gap-1 text-xs text-muted-foreground">
                          {t('ws.autoOutbound.field.maxRetries', locale)}
                          <input
                            type="number"
                            min={0}
                            max={5}
                            value={values.retry_policy[key].max_retries}
                            onChange={(e) => patchRetry(key, 'max_retries', Number(e.target.value))}
                            className="h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground"
                          />
                        </label>
                        <label className="grid gap-1 text-xs text-muted-foreground">
                          {t('ws.autoOutbound.field.intervalMinutes', locale)}
                          <input
                            type="number"
                            min={1}
                            value={values.retry_policy[key].interval_minutes}
                            onChange={(e) => patchRetry(key, 'interval_minutes', Number(e.target.value))}
                            className="h-9 rounded-md border border-border bg-background px-3 text-sm text-foreground"
                          />
                        </label>
                      </div>
                    </div>
                  ))}
                  <label className="grid gap-1.5 text-sm">
                    <span className="font-medium">{t('ws.autoOutbound.field.dailyLimit', locale)}</span>
                    <input
                      type="number"
                      min={1}
                      max={10}
                      value={values.daily_per_number_limit}
                      onChange={(e) => patch({ daily_per_number_limit: Number(e.target.value) })}
                      className="h-10 rounded-md border border-border bg-background px-3"
                    />
                  </label>
                  <div className="flex items-start justify-between gap-4 rounded-md border border-border p-3">
                    <div className="min-w-0">
                      <div className="text-sm font-medium">
                        {t('ws.autoOutbound.field.autoResumeOnAppend', locale)}
                      </div>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        {t('ws.autoOutbound.field.autoResumeOnAppendHint', locale)}
                      </p>
                    </div>
                    <Switch
                      checked={values.auto_resume_on_target_append}
                      onCheckedChange={(checked) => patch({ auto_resume_on_target_append: checked })}
                      aria-label={t('ws.autoOutbound.field.autoResumeOnAppend', locale)}
                    />
                  </div>
                </div>
              </section>
            </>
          )}
        </div>
      </div>

      <div className="flex shrink-0 items-center justify-between border-t border-border px-6 py-4">
        <button
          type="button"
          onClick={handleCancel}
          className="h-9 rounded-md px-4 text-sm text-muted-foreground hover:text-foreground"
        >
          {t('ws.autoOutbound.action.cancel', locale)}
        </button>
        <div className="flex items-center gap-2">
          {step > 1 && (
            <button
              type="button"
              onClick={() => setStep((prev) => (prev - 1) as 1 | 2 | 3)}
              className="h-9 rounded-md border border-border px-4 text-sm"
            >
              {t('ws.autoOutbound.action.prev', locale)}
            </button>
          )}
          <button
            type="button"
            disabled={submitting}
            onClick={() => {
              // Full payload is required by the create/update API, including schedule fields.
              if (!validateStep(3)) return
              void onSaveDraft(payload())
            }}
            className="h-9 rounded-md border border-border px-4 text-sm disabled:opacity-50"
          >
            {t('ws.autoOutbound.action.saveDraft', locale)}
          </button>
          {step < 3 ? (
            <button
              type="button"
              onClick={() => {
                if (validateStep(step)) setStep((prev) => (prev + 1) as 1 | 2 | 3)
              }}
              className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground"
            >
              {t('ws.autoOutbound.action.next', locale)}
            </button>
          ) : (
            <button
              type="button"
              disabled={submitting}
              onClick={() => {
                if (!validateStep(3)) return
                void onStart(payload())
              }}
              className="h-9 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground disabled:opacity-50"
            >
              {t(mode === 'create' ? 'ws.autoOutbound.action.create' : 'ws.autoOutbound.action.start', locale)}
            </button>
          )}
        </div>
      </div>

      <Dialog open={leaveOpen} onOpenChange={setLeaveOpen}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>{t('ws.autoOutbound.leaveConfirm.title', locale)}</DialogTitle>
            <DialogDescription>{t('ws.autoOutbound.leaveConfirm.body', locale)}</DialogDescription>
          </DialogHeader>
          <DialogFooter className="pb-0">
            <button
              type="button"
              onClick={() => setLeaveOpen(false)}
              className="inline-flex h-10 items-center rounded-md border border-border px-3 text-sm"
            >
              {t('ws.autoOutbound.action.cancel', locale)}
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="inline-flex h-10 items-center rounded-md bg-primary px-3 text-sm text-primary-foreground"
            >
              {t('ws.autoOutbound.leaveConfirm.confirm', locale)}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
