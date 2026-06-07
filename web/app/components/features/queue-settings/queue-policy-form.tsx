'use client'

import { useEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Locale } from '@/context/locale-store'
import type {
  QueueAssignmentStrategy,
  QueueChannel,
  QueuePolicy,
  QueuePolicyScopeType,
  QueuePolicyUpsertPayload,
} from '@/models/queue-policy'
import {
  DEFAULT_QUEUE_ASSIGNMENT_STRATEGY,
  QUEUE_ASSIGNMENT_STRATEGIES_BY_CHANNEL,
  isQueueAssignmentStrategySupported,
} from '@/models/queue-policy'

export type QueuePolicyDraft = {
  assignment_strategy: QueueAssignmentStrategy
  max_waiting_count: string
  max_wait_seconds: string
}

export type QueuePolicyFieldErrors = {
  max_waiting_count?: string
  max_wait_seconds?: string
}

export function channelLabel(channel: QueueChannel, locale: Locale): string {
  return t(`queue.channel.${channel}`, locale)
}

export function strategyLabel(strategy: QueueAssignmentStrategy, locale: Locale): string {
  return t(`queue.strategy.${strategy}`, locale)
}

export function formatQueueLimit(value: number | null | undefined, locale: Locale): string {
  return value == null ? t('queue.limit.unlimited', locale) : String(value)
}

export function formatQueueWait(value: number | null | undefined, locale: Locale): string {
  return value == null ? t('queue.limit.unlimited', locale) : t('queue.seconds', locale, { value })
}

export function createQueuePolicyDraft(
  channel: QueueChannel,
  policy?: QueuePolicy,
  fallback?: QueuePolicy,
): QueuePolicyDraft {
  const rawPolicyStrategy = policy?.assignment_strategy
  const rawFallbackStrategy = fallback?.assignment_strategy
  const policyStrategy = isQueueAssignmentStrategySupported(channel, rawPolicyStrategy)
    ? rawPolicyStrategy
    : undefined
  const fallbackStrategy = isQueueAssignmentStrategySupported(channel, rawFallbackStrategy)
    ? rawFallbackStrategy
    : undefined
  return {
    assignment_strategy:
      policyStrategy ??
      fallbackStrategy ??
      DEFAULT_QUEUE_ASSIGNMENT_STRATEGY,
    max_waiting_count: policy?.max_waiting_count != null ? String(policy.max_waiting_count) : '',
    max_wait_seconds: policy?.max_wait_seconds != null ? String(policy.max_wait_seconds) : '',
  }
}

export function parseOptionalPositiveInt(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  return Number(trimmed)
}

export function validateQueuePolicyDraft(draft: QueuePolicyDraft, locale: Locale): QueuePolicyFieldErrors {
  const errors: QueuePolicyFieldErrors = {}
  const maxWaiting = parseOptionalPositiveInt(draft.max_waiting_count)
  if (maxWaiting != null && (!Number.isInteger(maxWaiting) || maxWaiting < 1)) {
    errors.max_waiting_count = t('queue.validation.positiveInteger', locale)
  } else if (maxWaiting != null && maxWaiting > 99999) {
    errors.max_waiting_count = t('queue.validation.maxWaitingRange', locale)
  }
  const maxWait = parseOptionalPositiveInt(draft.max_wait_seconds)
  if (maxWait != null && (!Number.isInteger(maxWait) || maxWait < 1)) {
    errors.max_wait_seconds = t('queue.validation.positiveInteger', locale)
  } else if (maxWait != null && maxWait > 86400) {
    errors.max_wait_seconds = t('queue.validation.maxWaitRange', locale)
  }
  return errors
}

export function buildQueuePolicyPayload({
  channel,
  scopeType,
  scopeId,
  enabled,
  includeStrategy,
  draft,
}: {
  channel: QueueChannel
  scopeType: QueuePolicyScopeType
  scopeId?: number | null
  enabled: boolean
  includeStrategy: boolean
  draft: QueuePolicyDraft
}): QueuePolicyUpsertPayload {
  return {
    channel,
    scope_type: scopeType,
    scope_id: scopeType === 'global' ? null : scopeId ?? null,
    enabled,
    assignment_strategy: includeStrategy ? draft.assignment_strategy : null,
    max_waiting_count: parseOptionalPositiveInt(draft.max_waiting_count),
    max_wait_seconds: parseOptionalPositiveInt(draft.max_wait_seconds),
    config: {},
  }
}

function draftEqualsPolicy(draft: QueuePolicyDraft, policy: QueuePolicy | undefined): boolean {
  const baseline = createQueuePolicyDraft(policy?.channel ?? 'online_chat', policy)
  return (
    draft.assignment_strategy === baseline.assignment_strategy &&
    draft.max_waiting_count === baseline.max_waiting_count &&
    draft.max_wait_seconds === baseline.max_wait_seconds
  )
}

type QueuePolicyFormProps = {
  channel: QueueChannel
  title: string
  policy?: QueuePolicy
  saving?: boolean
  onSave: (payload: QueuePolicyUpsertPayload) => Promise<void>
}

export function QueuePolicyForm({ channel, title, policy, saving = false, onSave }: QueuePolicyFormProps) {
  const { locale } = useLocaleStore()
  const initialDraft = useMemo(() => createQueuePolicyDraft(channel, policy), [channel, policy])
  const [draft, setDraft] = useState<QueuePolicyDraft>(initialDraft)
  const [errors, setErrors] = useState<QueuePolicyFieldErrors>({})

  useEffect(() => {
    setDraft(initialDraft)
    setErrors({})
  }, [initialDraft])

  const dirty = !draftEqualsPolicy(draft, policy)
  const strategies = QUEUE_ASSIGNMENT_STRATEGIES_BY_CHANNEL[channel]

  const handleSave = async () => {
    const nextErrors = validateQueuePolicyDraft(draft, locale)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return
    await onSave(buildQueuePolicyPayload({
      channel,
      scopeType: 'global',
      enabled: true,
      includeStrategy: true,
      draft,
    }))
  }

  return (
    <section className="flex max-w-3xl flex-col gap-5 rounded-lg border border-border p-6">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      <div className="flex max-w-[280px] flex-col gap-2">
        <Label>{t('queue.field.strategy', locale)}</Label>
        <select
          value={draft.assignment_strategy}
          onChange={(e) => setDraft((prev) => ({
            ...prev,
            assignment_strategy: e.target.value as QueueAssignmentStrategy,
          }))}
          className="h-10 rounded-lg border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        >
          {strategies.map((strategy) => (
            <option key={strategy} value={strategy}>{strategyLabel(strategy, locale)}</option>
          ))}
        </select>
      </div>
      <div className="flex max-w-[220px] flex-col gap-2">
        <Label>{t('queue.field.maxWaiting', locale)}</Label>
        <Input
          value={draft.max_waiting_count}
          onChange={(e) => {
            setDraft((prev) => ({ ...prev, max_waiting_count: e.target.value }))
            setErrors((prev) => ({ ...prev, max_waiting_count: undefined }))
          }}
          inputMode="numeric"
          placeholder={t('queue.placeholder.unlimited', locale)}
          aria-invalid={!!errors.max_waiting_count}
          className="h-10"
        />
        {errors.max_waiting_count && <span className="text-xs text-destructive">{errors.max_waiting_count}</span>}
      </div>
      <div className="flex flex-col gap-2">
        <Label>{t('queue.field.maxWait', locale)}</Label>
        <div className="flex items-center gap-2">
          <Input
            value={draft.max_wait_seconds}
            onChange={(e) => {
              setDraft((prev) => ({ ...prev, max_wait_seconds: e.target.value }))
              setErrors((prev) => ({ ...prev, max_wait_seconds: undefined }))
            }}
            inputMode="numeric"
            placeholder={t('queue.placeholder.unlimited', locale)}
            aria-invalid={!!errors.max_wait_seconds}
            className="h-10 max-w-[220px]"
          />
          <span className="text-sm text-muted-foreground">{t('queue.unit.seconds', locale)}</span>
        </div>
        {errors.max_wait_seconds && <span className="text-xs text-destructive">{errors.max_wait_seconds}</span>}
      </div>
      <div>
        <Button type="button" onClick={handleSave} disabled={saving || !dirty}>
          {saving ? t('queue.saving', locale) : t('queue.save', locale)}
        </Button>
      </div>
    </section>
  )
}
