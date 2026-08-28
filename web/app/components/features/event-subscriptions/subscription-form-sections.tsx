'use client'

import { IconKey, IconSend } from '@tabler/icons-react'
import type { EventSubscription, EventSubscriptionTestResult } from '@/models/event-subscription'
import type { EventSubscriptionFormValue } from '@/utils/event-subscription-validation'
import type { Locale } from '@/lib/languages'
import { t } from '@/utils/i18n'

type Errors = Partial<Record<keyof EventSubscriptionFormValue, string>>

function Field({ label, value, maxLength, error, mono, onChange }: {
  label: string
  value: string
  maxLength: number
  error?: string
  mono?: boolean
  onChange: (value: string) => void
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-foreground/80">{label}</span>
      <input
        value={value}
        maxLength={maxLength}
        onChange={(event) => onChange(event.target.value)}
        className={`mt-1.5 h-10 w-full rounded-lg border bg-background px-3 text-sm outline-none focus:border-foreground/40 ${error ? 'border-destructive' : 'border-border'} ${mono ? 'font-mono text-xs' : ''}`}
      />
      {error && <span className="mt-1.5 block text-xs text-destructive">{error}</span>}
    </label>
  )
}

function FormSection({ title, children, last = false }: { title: string; children: React.ReactNode; last?: boolean }) {
  return (
    <section className={`py-7 ${last ? '' : 'border-b border-border'}`}>
      <h2 className="text-base font-semibold">{title}</h2>
      <div className="mt-5">{children}</div>
    </section>
  )
}

export function SubscriptionBasicSection({ value, errors, locale, onChange }: {
  value: EventSubscriptionFormValue
  errors: Errors
  locale: Locale
  onChange: (field: keyof EventSubscriptionFormValue, value: string) => void
}) {
  return (
    <FormSection title={t('eventSubs.form.basic', locale)}>
      <div className="space-y-5">
        <Field label={t('eventSubs.form.name', locale)} value={value.name} maxLength={80} error={errors.name} onChange={(next) => onChange('name', next)} />
        <Field label="Endpoint URL" value={value.endpoint_url} maxLength={2048} error={errors.endpoint_url} mono onChange={(next) => onChange('endpoint_url', next)} />
        <Field label={t('eventSubs.form.description', locale)} value={value.description} maxLength={200} error={errors.description} onChange={(next) => onChange('description', next)} />
      </div>
    </FormSection>
  )
}

function resultText(result: EventSubscriptionTestResult, locale: Locale) {
  if (result.status === 'succeeded') {
    return t('eventSubs.test.result.success', locale, { status: result.http_status ?? '—', duration: result.duration_ms })
  }
  return t('eventSubs.test.result.failed', locale, { type: result.error_type ?? 'unknown' })
}

export function SubscriptionSecuritySection({ record, locale, endpointChanged, testResult, rotating, testing, onRotate, onTest }: {
  record: EventSubscription | null
  locale: Locale
  endpointChanged: boolean
  testResult: EventSubscriptionTestResult | null
  rotating: boolean
  testing: boolean
  onRotate: () => void
  onTest: () => void
}) {
  return (
    <FormSection title={t('eventSubs.form.security', locale)} last>
      <div>
        <p className="text-sm font-medium text-foreground/80">Webhook Secret</p>
        <div className="mt-1.5 flex h-10 items-center justify-between rounded-lg border border-border bg-muted/30 px-3 font-mono text-xs">
          <span>{record?.masked_secret ?? t('eventSubs.secret.afterSave', locale)}</span><IconKey size={16} className="text-muted-foreground" />
        </div>
        <button className="mt-3 h-9 rounded-lg border border-border px-4 text-sm font-medium disabled:opacity-50" disabled={!record || rotating} onClick={onRotate}>
          {rotating ? t('eventSubs.pending', locale) : t('eventSubs.rotate', locale)}
        </button>
      </div>
      <div className="mt-6 border-t border-border pt-6">
        <p className="text-sm font-medium text-foreground/80">{t('eventSubs.test.title', locale)}</p>
        {endpointChanged && <p className="mt-2 text-xs text-warning">{t('eventSubs.test.endpointChanged', locale)}</p>}
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button className="flex h-9 items-center gap-2 rounded-lg border border-border px-4 text-sm font-medium disabled:opacity-50" disabled={!record || testing || endpointChanged} onClick={onTest}>
            <IconSend size={16} />{testing ? t('eventSubs.test.sending', locale) : t('eventSubs.test.send', locale)}
          </button>
          {testResult && <span className={`text-xs ${testResult.status === 'succeeded' ? 'text-success' : 'text-destructive'}`}>{resultText(testResult, locale)}</span>}
        </div>
      </div>
    </FormSection>
  )
}
