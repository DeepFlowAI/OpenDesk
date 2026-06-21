'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { ArrowLeft } from 'lucide-react'
import { Checkbox } from '@/components/ui/checkbox'
import { Switch } from '@/components/ui/switch'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import type { VisitorTimeoutCloseConfig, VisitorTimeoutClosePayload } from '@/models/visitor-timeout-close'
import {
  useSaveVisitorTimeoutCloseSettings,
  useVisitorTimeoutCloseSettings,
} from '@/service/use-visitor-timeout-close'
import { t } from '@/utils/i18n'

const MINUTES_MIN = 1
const MINUTES_MAX = 1440
const CONTENT_MAX = 500

function clonePayload(config: VisitorTimeoutCloseConfig): VisitorTimeoutClosePayload {
  return {
    enabled: config.enabled,
    first_normal_minutes: config.first_normal_minutes,
    close_normal_minutes: config.close_normal_minutes,
    vip_enabled: config.vip_enabled,
    first_vip_minutes: config.first_vip_minutes,
    close_vip_minutes: config.close_vip_minutes,
    first_reminder_content: config.first_reminder_content,
    close_reminder_content: config.close_reminder_content,
    notify_agent: config.notify_agent,
    notify_visitor: config.notify_visitor,
  }
}

function normalizePayload(form: VisitorTimeoutClosePayload): VisitorTimeoutClosePayload {
  return {
    ...form,
    first_reminder_content: form.first_reminder_content.trim(),
    close_reminder_content: form.close_reminder_content.trim(),
  }
}

function validate(form: VisitorTimeoutClosePayload, locale: Locale): Record<string, string> {
  const errors: Record<string, string> = {}
  const minutes = [
    'first_normal_minutes',
    'close_normal_minutes',
    'first_vip_minutes',
    'close_vip_minutes',
  ] as const
  minutes.forEach((key) => {
    const value = form[key]
    if (!Number.isInteger(value) || value < MINUTES_MIN || value > MINUTES_MAX) {
      errors[key] = t('visitorTimeout.validation.minutes', locale)
    }
  })
  if (form.close_normal_minutes <= form.first_normal_minutes) {
    errors.close_normal_minutes = t('visitorTimeout.validation.closeAfterFirst', locale)
  }
  if (form.vip_enabled && form.close_vip_minutes <= form.first_vip_minutes) {
    errors.close_vip_minutes = t('visitorTimeout.validation.closeAfterFirst', locale)
  }
  if (!form.first_reminder_content.trim()) {
    errors.first_reminder_content = t('visitorTimeout.validation.contentRequired', locale)
  } else if (form.first_reminder_content.trim().length > CONTENT_MAX) {
    errors.first_reminder_content = t('visitorTimeout.validation.contentMax', locale, { max: CONTENT_MAX })
  }
  if (!form.close_reminder_content.trim()) {
    errors.close_reminder_content = t('visitorTimeout.validation.contentRequired', locale)
  } else if (form.close_reminder_content.trim().length > CONTENT_MAX) {
    errors.close_reminder_content = t('visitorTimeout.validation.contentMax', locale, { max: CONTENT_MAX })
  }
  if (!form.notify_agent && !form.notify_visitor) {
    errors.notify = t('visitorTimeout.validation.notifyTarget', locale)
  }
  return errors
}

function FieldError({ text }: { text?: string }) {
  if (!text) return null
  return <p className="text-xs text-destructive">{text}</p>
}

function SectionDivider() {
  return <div className="h-px w-full bg-border" />
}

function SectionHeading({ title, description }: { title: string; description?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
    </div>
  )
}

function SwitchRow({
  label,
  checked,
  disabled,
  onCheckedChange,
}: {
  label: string
  checked: boolean
  disabled?: boolean
  onCheckedChange: (value: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm font-medium text-foreground">{label}</span>
      <Switch checked={checked} disabled={disabled} onCheckedChange={onCheckedChange} />
    </div>
  )
}

function NumberField({
  label,
  value,
  disabled,
  error,
  locale,
  onChange,
}: {
  label: string
  value: number
  disabled?: boolean
  error?: string
  locale: Locale
  onChange: (value: number) => void
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-medium text-foreground">{label}</span>
      <div
        className={`flex h-10 items-center rounded-lg border border-border bg-background px-3.5 focus-within:border-primary focus-within:ring-1 focus-within:ring-ring ${disabled ? 'opacity-50' : ''}`}
      >
        <input
          type="number"
          min={MINUTES_MIN}
          max={MINUTES_MAX}
          step={1}
          value={value}
          disabled={disabled}
          onChange={(event) => {
            const next = Number(event.target.value)
            onChange(Number.isFinite(next) ? Math.trunc(next) : 0)
          }}
          className="h-full min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none disabled:cursor-not-allowed"
        />
        <span className="ml-2 shrink-0 text-sm text-muted-foreground">{t('visitorTimeout.unit.minutes', locale)}</span>
      </div>
      <FieldError text={error} />
    </div>
  )
}

function ContentField({
  label,
  value,
  error,
  onChange,
}: {
  label: string
  value: string
  error?: string
  onChange: (value: string) => void
}) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-sm font-medium text-foreground">{label}</span>
      <textarea
        value={value}
        maxLength={CONTENT_MAX}
        onChange={(event) => onChange(event.target.value)}
        className="h-20 w-full resize-none rounded-lg border border-border bg-background px-3.5 py-2.5 text-sm text-foreground outline-none focus:border-primary focus:ring-1 focus:ring-ring"
      />
      <div className="flex items-center justify-between gap-3">
        <FieldError text={error} />
        <span className="ml-auto text-xs text-muted-foreground">{value.trim().length}/{CONTENT_MAX}</span>
      </div>
    </div>
  )
}

function PageHeader({
  locale,
  dirty,
  hasErrors,
  saving,
  onBack,
  onSave,
}: {
  locale: Locale
  dirty: boolean
  hasErrors: boolean
  saving: boolean
  onBack: () => void
  onSave: () => void
}) {
  return (
    <div className="sticky -top-8 z-20 flex h-14 shrink-0 items-center justify-between gap-4 border-b border-border bg-white px-6">
      <button type="button" onClick={onBack} className="flex min-w-0 items-center gap-2 text-left">
        <ArrowLeft size={20} className="shrink-0 text-muted-foreground" />
        <span className="truncate text-base font-semibold text-foreground">
          {t('visitorTimeout.page.title', locale)}
        </span>
      </button>
      <button
        type="button"
        onClick={onSave}
        disabled={!dirty || hasErrors || saving}
        className="inline-flex h-9 shrink-0 items-center rounded-lg bg-primary px-5 text-sm font-medium text-primary-foreground hover:bg-primary/80 disabled:opacity-40"
      >
        {saving ? t('visitorTimeout.saving', locale) : t('visitorTimeout.save', locale)}
      </button>
    </div>
  )
}

export default function VisitorTimeoutClosePage() {
  const router = useRouter()
  const { locale } = useLocaleStore()
  const { data, isLoading, isError, refetch } = useVisitorTimeoutCloseSettings()
  const saveMut = useSaveVisitorTimeoutCloseSettings()
  const [form, setForm] = useState<VisitorTimeoutClosePayload | null>(null)
  const [baseline, setBaseline] = useState<VisitorTimeoutClosePayload | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  useEffect(() => {
    if (!data) return
    const next = clonePayload(data)
    setForm(next)
    setBaseline(next)
  }, [data])

  const errors = useMemo(() => (form ? validate(form, locale) : {}), [form, locale])
  const hasErrors = Object.keys(errors).length > 0
  const dirty = !!form && !!baseline && JSON.stringify(form) !== JSON.stringify(baseline)

  const showToast = (type: 'success' | 'error', text: string) => {
    setToast({ type, text })
    setTimeout(() => setToast(null), 3000)
  }

  const updateForm = <K extends keyof VisitorTimeoutClosePayload>(key: K, value: VisitorTimeoutClosePayload[K]) => {
    setForm((current) => (current ? { ...current, [key]: value } : current))
  }

  const handleBack = () => {
    if (dirty && !window.confirm(t('visitorTimeout.leaveConfirm', locale))) return
    router.push('/online-service/conversation-settings')
  }

  const handleSave = async () => {
    if (!form || hasErrors) return
    try {
      const saved = await saveMut.mutateAsync(normalizePayload(form))
      const next = clonePayload(saved)
      setForm(next)
      setBaseline(next)
      showToast('success', t('visitorTimeout.saveSuccess', locale))
    } catch {
      showToast('error', t('visitorTimeout.saveFailed', locale))
    }
  }

  if (isError) {
    return (
      <div className="-m-8 flex flex-col">
        <PageHeader
          locale={locale}
          dirty={false}
          hasErrors={false}
          saving={false}
          onBack={() => router.push('/online-service/conversation-settings')}
          onSave={() => {}}
        />
        <div className="flex flex-col gap-4 px-8 py-8">
          <p className="text-sm text-muted-foreground">{t('visitorTimeout.loadFailed', locale)}</p>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => refetch()}
              className="inline-flex h-9 items-center rounded-lg border border-border px-4 text-sm font-medium text-foreground hover:bg-accent"
            >
              {t('vc.retry', locale)}
            </button>
            <button
              type="button"
              onClick={() => router.push('/online-service/conversation-settings')}
              className="inline-flex h-9 items-center rounded-lg px-4 text-sm font-medium text-muted-foreground hover:bg-accent"
            >
              {t('visitorTimeout.back', locale)}
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (isLoading || !form) {
    return (
      <div className="-m-8 flex flex-col">
        <PageHeader
          locale={locale}
          dirty={false}
          hasErrors={false}
          saving={false}
          onBack={() => router.push('/online-service/conversation-settings')}
          onSave={() => {}}
        />
        <div className="flex flex-col gap-7 px-8 py-8">
          <div className="h-10 w-48 animate-pulse rounded-lg bg-muted" />
          <div className="h-10 w-full animate-pulse rounded-lg bg-muted" />
          <div className="h-px w-full bg-border" />
          <div className="h-10 w-full animate-pulse rounded-lg bg-muted" />
          <div className="h-20 w-full animate-pulse rounded-lg bg-muted" />
        </div>
      </div>
    )
  }

  return (
    <div className="-m-8 flex flex-col">
      <PageHeader
        locale={locale}
        dirty={dirty}
        hasErrors={hasErrors}
        saving={saveMut.isPending}
        onBack={handleBack}
        onSave={handleSave}
      />

      {toast && (
        <div
          className={`mx-8 mt-4 rounded-lg px-4 py-3 text-sm ${
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}
        >
          {toast.text}
        </div>
      )}

      <div className="flex flex-col gap-7 px-8 pb-8 pt-8">
        <section className="flex flex-col gap-5">
          <SectionHeading
            title={t('visitorTimeout.section.basic', locale)}
            description={t('visitorTimeout.section.basicDescription', locale)}
          />
          <SwitchRow
            label={t('visitorTimeout.field.enabled', locale)}
            checked={form.enabled}
            onCheckedChange={(value) => updateForm('enabled', value)}
          />
        </section>

        <SectionDivider />

        <section className="flex flex-col gap-5">
          <SectionHeading title={t('visitorTimeout.section.vip', locale)} />
          <SwitchRow
            label={t('visitorTimeout.field.vipEnabled', locale)}
            checked={form.vip_enabled}
            onCheckedChange={(value) => updateForm('vip_enabled', value)}
          />
          <p className="text-[13px] leading-5 text-muted-foreground">
            {t('visitorTimeout.section.vipDescription', locale)}
          </p>
        </section>

        <SectionDivider />

        <section className="flex flex-col gap-5">
          <SectionHeading title={t('visitorTimeout.section.firstReminder', locale)} />
          <NumberField
            label={t('visitorTimeout.field.firstNormal', locale)}
            value={form.first_normal_minutes}
            error={errors.first_normal_minutes}
            locale={locale}
            onChange={(value) => updateForm('first_normal_minutes', value)}
          />
          <NumberField
            label={t('visitorTimeout.field.firstVip', locale)}
            value={form.first_vip_minutes}
            disabled={!form.vip_enabled}
            error={errors.first_vip_minutes}
            locale={locale}
            onChange={(value) => updateForm('first_vip_minutes', value)}
          />
          <ContentField
            label={t('visitorTimeout.field.firstContent', locale)}
            value={form.first_reminder_content}
            error={errors.first_reminder_content}
            onChange={(value) => updateForm('first_reminder_content', value)}
          />
        </section>

        <SectionDivider />

        <section className="flex flex-col gap-5">
          <SectionHeading title={t('visitorTimeout.section.autoClose', locale)} />
          <NumberField
            label={t('visitorTimeout.field.closeNormal', locale)}
            value={form.close_normal_minutes}
            error={errors.close_normal_minutes}
            locale={locale}
            onChange={(value) => updateForm('close_normal_minutes', value)}
          />
          <NumberField
            label={t('visitorTimeout.field.closeVip', locale)}
            value={form.close_vip_minutes}
            disabled={!form.vip_enabled}
            error={errors.close_vip_minutes}
            locale={locale}
            onChange={(value) => updateForm('close_vip_minutes', value)}
          />
          <ContentField
            label={t('visitorTimeout.field.closeContent', locale)}
            value={form.close_reminder_content}
            error={errors.close_reminder_content}
            onChange={(value) => updateForm('close_reminder_content', value)}
          />
          <p className="text-[13px] leading-5 text-muted-foreground">{t('visitorTimeout.autoCloseNote', locale)}</p>
        </section>

        <SectionDivider />

        <section className="flex flex-col gap-5">
          <SectionHeading
            title={t('visitorTimeout.section.notify', locale)}
            description={t('visitorTimeout.section.notifyDescription', locale)}
          />
          <label className="flex items-center gap-2.5 text-sm text-foreground">
            <Checkbox
              checked={form.notify_agent}
              onCheckedChange={(checked) => updateForm('notify_agent', checked === true)}
            />
            {t('visitorTimeout.field.notifyAgent', locale)}
          </label>
          <label className="flex items-center gap-2.5 text-sm text-foreground">
            <Checkbox
              checked={form.notify_visitor}
              onCheckedChange={(checked) => updateForm('notify_visitor', checked === true)}
            />
            {t('visitorTimeout.field.notifyVisitor', locale)}
          </label>
          <FieldError text={errors.notify} />
        </section>
      </div>
    </div>
  )
}
