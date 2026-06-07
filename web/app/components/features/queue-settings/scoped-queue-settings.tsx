'use client'

import { useEffect, useMemo, useState } from 'react'
import { Switch } from '@/components/ui/switch'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type {
  QueueChannel,
  QueuePolicy,
  QueuePolicyScopeType,
  QueuePolicyUpsertPayload,
  QueueAssignmentStrategy,
} from '@/models/queue-policy'
import { QUEUE_CHANNELS, QUEUE_ASSIGNMENT_STRATEGIES_BY_CHANNEL } from '@/models/queue-policy'
import {
  buildQueuePolicyPayload,
  channelLabel,
  createQueuePolicyDraft,
  formatQueueLimit,
  formatQueueWait,
  strategyLabel,
  validateQueuePolicyDraft,
  type QueuePolicyDraft,
} from './queue-policy-form'

type ScopedDraft = QueuePolicyDraft & {
  enabled: boolean
  dirty: boolean
}

type ScopedQueueSettingsProps = {
  title: string
  scopeType: Extract<QueuePolicyScopeType, 'employee_group' | 'employee'>
  scopeId: number
  defaultPolicies?: QueuePolicy[]
  scopedPolicies?: QueuePolicy[]
  includeStrategy: boolean
  disabled?: boolean
  disabledHint?: string
  onChange: (payloads: QueuePolicyUpsertPayload[], valid: boolean) => void
}

function findPolicy(policies: QueuePolicy[] | undefined, channel: QueueChannel): QueuePolicy | undefined {
  return policies?.find((policy) => policy.channel === channel)
}

function createScopedDrafts(
  defaultPolicies: QueuePolicy[] | undefined,
  scopedPolicies: QueuePolicy[] | undefined,
): Record<QueueChannel, ScopedDraft> {
  return QUEUE_CHANNELS.reduce((acc, channel) => {
    const defaultPolicy = findPolicy(defaultPolicies, channel)
    const scopedPolicy = findPolicy(scopedPolicies, channel)
    const enabled = scopedPolicy?.enabled ?? false
    const source = enabled ? scopedPolicy : undefined
    acc[channel] = {
      ...createQueuePolicyDraft(channel, source, defaultPolicy),
      enabled,
      dirty: false,
    }
    return acc
  }, {} as Record<QueueChannel, ScopedDraft>)
}

function policySignature(policies: QueuePolicy[] | undefined): string {
  return JSON.stringify((policies ?? []).map((policy) => ({
    channel: policy.channel,
    enabled: policy.enabled,
    assignment_strategy: policy.assignment_strategy,
    max_waiting_count: policy.max_waiting_count,
    max_wait_seconds: policy.max_wait_seconds,
  })))
}

export function ScopedQueueSettings({
  title,
  scopeType,
  scopeId,
  defaultPolicies,
  scopedPolicies,
  includeStrategy,
  disabled = false,
  disabledHint,
  onChange,
}: ScopedQueueSettingsProps) {
  const { locale } = useLocaleStore()
  const defaultSignature = useMemo(() => policySignature(defaultPolicies), [defaultPolicies])
  const scopedSignature = useMemo(() => policySignature(scopedPolicies), [scopedPolicies])
  const [drafts, setDrafts] = useState<Record<QueueChannel, ScopedDraft>>(() =>
    createScopedDrafts(defaultPolicies, scopedPolicies)
  )

  useEffect(() => {
    setDrafts(createScopedDrafts(defaultPolicies, scopedPolicies))
  }, [defaultSignature, scopedSignature, defaultPolicies, scopedPolicies])

  useEffect(() => {
    const payloads: QueuePolicyUpsertPayload[] = []
    let valid = true
    for (const channel of QUEUE_CHANNELS) {
      const draft = drafts[channel]
      if (!draft.dirty) continue
      const errors = validateQueuePolicyDraft(draft, locale)
      if (Object.keys(errors).length > 0) valid = false
      payloads.push(buildQueuePolicyPayload({
        channel,
        scopeType,
        scopeId,
        enabled: draft.enabled,
        includeStrategy,
        draft,
      }))
    }
    onChange(payloads, valid)
  }, [drafts, includeStrategy, locale, onChange, scopeId, scopeType])

  const updateDraft = (channel: QueueChannel, patch: Partial<ScopedDraft>) => {
    setDrafts((prev) => ({
      ...prev,
      [channel]: {
        ...prev[channel],
        ...patch,
        dirty: true,
      },
    }))
  }

  return (
    <section className="flex max-w-3xl flex-col gap-4">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      {QUEUE_CHANNELS.map((channel) => {
        const draft = drafts[channel]
        const defaultPolicy = findPolicy(defaultPolicies, channel)
        const effectiveDraft = draft.enabled ? draft : createQueuePolicyDraft(channel, undefined, defaultPolicy)
        const errors = draft.enabled ? validateQueuePolicyDraft(draft, locale) : {}
        return (
          <div key={channel} className="flex flex-col gap-4 rounded-lg border border-border p-5">
            <div className="flex items-center justify-between gap-4">
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-semibold text-foreground">{channelLabel(channel, locale)}</h3>
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${
                    draft.enabled ? 'bg-green-50 text-green-700' : 'bg-muted text-muted-foreground'
                  }`}>
                    {draft.enabled ? t('queue.status.custom', locale) : t('queue.status.inherit', locale)}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  {draft.enabled ? t('queue.custom.enabledHint', locale) : t('queue.inheritHint', locale)}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm text-muted-foreground">{t('queue.customSwitch', locale)}</span>
                <Switch
                  checked={draft.enabled}
                  disabled={disabled}
                  onCheckedChange={(checked) => updateDraft(channel, { enabled: checked })}
                />
              </div>
            </div>

            {disabled && disabledHint && (
              <p className="rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground">{disabledHint}</p>
            )}

            {draft.enabled && (
              <div className="rounded-lg bg-muted/60 px-3 py-2 text-sm text-muted-foreground">
                {includeStrategy && (
                  <span>
                    {t('queue.summary.strategy', locale)}
                    {strategyLabel(effectiveDraft.assignment_strategy, locale)}
                  </span>
                )}
                <span className={includeStrategy ? 'ml-3' : undefined}>
                  {t('queue.summary.maxWaiting', locale)}
                  {formatQueueLimit(parseValue(effectiveDraft.max_waiting_count), locale)}
                </span>
                <span className="ml-3">
                  {t('queue.summary.maxWait', locale)}
                  {formatQueueWait(parseValue(effectiveDraft.max_wait_seconds), locale)}
                </span>
              </div>
            )}

            {draft.enabled && (
              <div className="flex flex-col gap-4">
                {includeStrategy && (
                  <div className="flex max-w-[280px] flex-col gap-2">
                    <label className="text-sm font-medium text-foreground/80">
                      {t('queue.field.strategy', locale)}
                    </label>
                    <select
                      value={draft.assignment_strategy}
                      disabled={disabled}
                      onChange={(e) => updateDraft(channel, {
                        assignment_strategy: e.target.value as QueueAssignmentStrategy,
                      })}
                      className="h-10 rounded-lg border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50"
                    >
                      {QUEUE_ASSIGNMENT_STRATEGIES_BY_CHANNEL[channel].map((strategy) => (
                        <option key={strategy} value={strategy}>{strategyLabel(strategy, locale)}</option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="flex max-w-[220px] flex-col gap-2">
                  <label className="text-sm font-medium text-foreground/80">
                    {t('queue.field.maxWaiting', locale)}
                  </label>
                  <input
                    value={draft.max_waiting_count}
                    disabled={disabled}
                    inputMode="numeric"
                    onChange={(e) => updateDraft(channel, { max_waiting_count: e.target.value })}
                    placeholder={t('queue.placeholder.unlimited', locale)}
                    className={`h-10 rounded-lg border px-3 text-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50 ${
                      errors.max_waiting_count ? 'border-destructive' : 'border-border'
                    }`}
                  />
                  {errors.max_waiting_count && (
                    <span className="text-xs text-destructive">{errors.max_waiting_count}</span>
                  )}
                </div>
                <div className="flex flex-col gap-2">
                  <label className="text-sm font-medium text-foreground/80">
                    {t('queue.field.maxWait', locale)}
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      value={draft.max_wait_seconds}
                      disabled={disabled}
                      inputMode="numeric"
                      onChange={(e) => updateDraft(channel, { max_wait_seconds: e.target.value })}
                      placeholder={t('queue.placeholder.unlimited', locale)}
                      className={`h-10 w-[220px] rounded-lg border px-3 text-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50 ${
                        errors.max_wait_seconds ? 'border-destructive' : 'border-border'
                      }`}
                    />
                    <span className="text-sm text-muted-foreground">{t('queue.unit.seconds', locale)}</span>
                  </div>
                  {errors.max_wait_seconds && (
                    <span className="text-xs text-destructive">{errors.max_wait_seconds}</span>
                  )}
                </div>
              </div>
            )}
          </div>
        )
      })}
    </section>
  )
}

function parseValue(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const parsed = Number(trimmed)
  return Number.isFinite(parsed) ? parsed : null
}
