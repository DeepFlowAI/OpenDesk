'use client'

import { useMemo, useState } from 'react'
import { IconFileDescription, IconPlus } from '@tabler/icons-react'
import { HTTPError } from 'ky'
import { toast } from 'sonner'

import { formatDateTime } from '@/app/components/features/engagement/outbound-task-ui'
import { FieldValueEditor } from '@/app/components/features/field-system'
import { useAuthStore } from '@/context/auth-store'
import { useCallCenterRuntime } from '@/context/call-center-runtime'
import { useLocaleStore } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import type { OutboundTarget, OutboundTargetStatus } from '@/models/outbound-task'
import { useCreateOutboundRecord } from '@/service/use-outbound-tasks'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import {
  activeOutboundTaskFields,
  isEmptyOutboundFieldValue,
  outboundFieldTreeNodes,
} from './outbound-task-fields'

type WrapUpStatus = Exclude<OutboundTargetStatus, 'calling'>

const WRAP_UP_STATUSES: WrapUpStatus[] = ['completed', 'redial', 'pending', 'do_not_call', 'invalid_number']

const STATUS_BUTTON_CLASS: Record<WrapUpStatus, { selected: string; unselected: string }> = {
  completed: { selected: 'bg-success text-white shadow-sm', unselected: 'bg-success/10 text-success' },
  redial: { selected: 'bg-warning text-white shadow-sm', unselected: 'bg-warning/15 text-foreground' },
  pending: { selected: 'bg-primary text-primary-foreground shadow-sm', unselected: 'border border-border bg-background' },
  do_not_call: { selected: 'bg-destructive text-white shadow-sm', unselected: 'bg-destructive/10 text-destructive' },
  invalid_number: { selected: 'bg-destructive text-white shadow-sm', unselected: 'bg-destructive/10 text-destructive' },
}

// Granular unanswered reasons reuse the call-record option translations.
const KNOWN_CALL_RESULTS = new Set([
  'agent_answered',
  'customer_short_abandon',
  'agent_no_answer',
  'customer_no_answer',
  'customer_busy',
  'customer_unreachable',
  'invalid_number',
  'ivr_customer_hangup',
  'bot_customer_hangup',
  'bot_completed',
  'canceled',
  'failed',
])

function formatTalkDuration(ms: number): string {
  const s = Math.floor(ms / 1000)
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`
}

export function MyOutboundWrapUp({
  target,
  fieldValues,
  onFieldChange,
  onSubmitted,
  onOpenScreenPop,
}: {
  target: OutboundTarget
  fieldValues: Record<string, unknown>
  onFieldChange: (fieldKey: string, value: unknown) => void
  onSubmitted: () => void
  onOpenScreenPop?: (target: OutboundTarget) => void
}) {
  const { locale } = useLocaleStore()
  const currentUser = useAuthStore((state) => state.user)
  const { currentRecord, callStart, wrapUpStartedAt, completeWrapUp, setCallSummaryTab } = useCallCenterRuntime()
  const createRecord = useCreateOutboundRecord()
  const [status, setStatus] = useState<WrapUpStatus>('pending')
  const [redialAt, setRedialAt] = useState('')
  const [redialError, setRedialError] = useState(false)

  const editableFields = useMemo(
    () => activeOutboundTaskFields(target.task?.fields).filter((field) => field.agent_editable),
    [target.task?.fields],
  )
  const canCreateTicket = hasPermission(currentUser, 'ticket.workspace.create')

  const answered = Boolean(currentRecord?.customer_connected_at)
  const rawCallResult = currentRecord?.call_result ?? null
  const callResultLabel = !currentRecord
    ? '—'
    : answered
      ? t('ws.outboundExec.records.answered', locale)
      : rawCallResult && KNOWN_CALL_RESULTS.has(rawCallResult)
        ? t(`ws.records.calls.option.callResult.${rawCallResult}`, locale)
        : t('ws.outboundExec.records.unanswered', locale)
  const talkDurationMs =
    currentRecord?.customer_agent_talk_duration_ms ??
    (callStart != null && wrapUpStartedAt != null ? Math.max(0, wrapUpStartedAt - callStart) : null)
  const startedAtIso = currentRecord?.started_at ?? (callStart != null ? new Date(callStart).toISOString() : null)

  const selectStatus = (next: WrapUpStatus) => {
    if (next === status) return
    if (next === 'do_not_call' && !window.confirm(t('ws.outboundExec.wrapUp.confirmDoNotCall', locale))) return
    if (next === 'invalid_number' && !window.confirm(t('ws.outboundExec.wrapUp.confirmInvalidNumber', locale))) return
    setStatus(next)
    if (next !== 'redial') setRedialError(false)
  }

  const openTicket = () => {
    setCallSummaryTab('ticket')
    onOpenScreenPop?.(target)
  }

  const submit = async () => {
    const missingField = editableFields.find(
      (field) => field.required && isEmptyOutboundFieldValue(fieldValues[field.key]),
    )
    if (missingField) {
      toast.error(t('ws.outboundExec.business.requiredMissing', locale, { name: missingField.name }))
      return
    }
    if (status === 'redial' && !redialAt) {
      setRedialError(true)
      return
    }
    try {
      await createRecord.mutateAsync({
        targetId: target.id,
        data: {
          call_record_id: currentRecord?.id ?? null,
          started_at: startedAtIso,
          duration_ms: answered ? talkDurationMs : null,
          answered,
          result: answered ? '已接通' : '未接通',
          target_status: status,
          next_follow_up_at: status === 'redial' && redialAt ? new Date(redialAt).toISOString() : null,
          field_values: Object.fromEntries(editableFields.map((field) => [field.key, fieldValues[field.key] ?? null])),
        },
      })
    } catch (err) {
      let taskChanged = false
      if (err instanceof HTTPError) {
        if (err.response.status === 403) {
          taskChanged = true
        } else if (err.response.status === 400) {
          try {
            const body = (await err.response.clone().json()) as { message?: string }
            taskChanged = (body.message ?? '').includes('not executable')
          } catch {
            // Fall through to the generic failure toast.
          }
        }
      }
      toast.error(t(taskChanged ? 'ws.outboundExec.exec.taskChanged' : 'ws.outboundExec.wrapUp.submitFailed', locale))
      return
    }
    toast.success(t('ws.outboundExec.wrapUp.submitSuccess', locale))
    if (status === 'redial' && redialAt) {
      toast.success(
        t('ws.outboundExec.wrapUp.redialScheduled', locale, { time: formatDateTime(new Date(redialAt).toISOString()) }),
      )
    }
    onSubmitted()
    completeWrapUp()
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">
        <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold">{t('ws.outboundExec.wrapUp.callFacts', locale)}</h3>
          <div className="grid grid-cols-3 gap-2.5">
            <InfoItem
              label={t('ws.outboundExec.wrapUp.callResult', locale)}
              value={callResultLabel}
              valueClassName={currentRecord && answered ? 'text-success' : undefined}
            />
            <InfoItem
              label={t('ws.outboundExec.wrapUp.talkDuration', locale)}
              value={answered && talkDurationMs != null ? formatTalkDuration(talkDurationMs) : '—'}
              valueClassName="font-mono"
            />
            <InfoItem
              label={t('ws.outboundExec.wrapUp.startedAt', locale)}
              value={startedAtIso ? formatDateTime(startedAtIso) : '—'}
              valueClassName="font-mono"
            />
          </div>
        </section>

        <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold">{t('ws.outboundExec.wrapUp.statusTitle', locale)}</h3>
          <div className="flex flex-wrap gap-2">
            {WRAP_UP_STATUSES.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => selectStatus(value)}
                className={cn(
                  'inline-flex h-9 items-center rounded-lg px-4 text-sm font-medium transition-colors',
                  status === value ? STATUS_BUTTON_CLASS[value].selected : STATUS_BUTTON_CLASS[value].unselected,
                )}
              >
                {t(`ws.outboundExec.status.target.${value}`, locale)}
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold">{t('ws.outboundExec.wrapUp.businessTitle', locale)}</h3>
          <div className="space-y-3">
            {editableFields.map((field) => (
              <div key={field.key}>
                <div className="mb-1 text-xs font-medium text-muted-foreground">
                  {field.name}
                  {field.required && <span className="text-destructive"> *</span>}
                </div>
                <FieldValueEditor
                  fieldType={field.field_type}
                  value={fieldValues[field.key]}
                  onChange={(value) => onFieldChange(field.key, value)}
                  typeConfig={field.type_config}
                  treeNodes={outboundFieldTreeNodes(field)}
                  className="min-w-0"
                />
              </div>
            ))}
            <div>
              <div className="mb-1 text-xs font-medium text-muted-foreground">
                {t('ws.outboundExec.wrapUp.redialAt', locale)}
                {status === 'redial' && <span className="text-destructive"> *</span>}
              </div>
              <input
                type="datetime-local"
                value={redialAt}
                disabled={status !== 'redial'}
                onChange={(event) => {
                  setRedialAt(event.target.value)
                  if (event.target.value) setRedialError(false)
                }}
                className={cn(
                  'h-9 w-full rounded-md border bg-background px-3 text-sm outline-none focus:border-primary disabled:border-dashed disabled:bg-muted/50 disabled:text-muted-foreground',
                  redialError ? 'border-destructive' : 'border-border',
                )}
              />
              {status !== 'redial' ? (
                <p className="mt-1 text-xs text-muted-foreground">{t('ws.outboundExec.wrapUp.redialHint', locale)}</p>
              ) : redialError ? (
                <p className="mt-1 text-xs text-destructive">{t('ws.outboundExec.wrapUp.redialRequired', locale)}</p>
              ) : null}
            </div>
          </div>
        </section>
      </div>

      <footer className="flex shrink-0 items-center justify-between border-t border-border bg-background px-5 py-3">
        {canCreateTicket && onOpenScreenPop ? (
          <button
            type="button"
            onClick={openTicket}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-muted-foreground hover:bg-muted"
          >
            <IconFileDescription size={15} />
            {t('ws.outboundExec.wrapUp.createTicket', locale)}
          </button>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={() => void submit()}
          disabled={createRecord.isPending}
          className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-primary px-5 text-sm font-medium text-primary-foreground shadow-sm disabled:opacity-60"
        >
          <IconPlus size={15} />
          {createRecord.isPending ? t('ws.outboundExec.wrapUp.submitting', locale) : t('ws.outboundExec.wrapUp.submit', locale)}
        </button>
      </footer>
    </div>
  )
}

function InfoItem({
  label,
  value,
  valueClassName,
}: {
  label: string
  value: string
  valueClassName?: string
}) {
  return (
    <div className="rounded-lg bg-muted/60 p-2.5">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn('mt-0.5 truncate text-xs font-medium', valueClassName)}>{value}</div>
    </div>
  )
}
