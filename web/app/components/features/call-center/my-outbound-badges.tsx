'use client'

import { cn } from '@/lib/utils'
import { useLocaleStore } from '@/context/locale-store'
import {
  OUTBOUND_TARGET_STATUS_LABELS,
  OUTBOUND_TASK_STATUS_LABELS,
  type OutboundTargetStatus,
  type OutboundTaskStatus,
} from '@/models/outbound-task'
import { t } from '@/utils/i18n'

const execTaskStatusClass: Partial<Record<OutboundTaskStatus, string>> = {
  active: 'bg-success/10 text-success',
  paused: 'bg-warning/10 text-warning',
}

const execTargetStatusClass: Record<OutboundTargetStatus, string> = {
  pending: 'bg-info/10 text-info',
  calling: 'bg-info/10 text-info',
  redial: 'bg-warning/10 text-warning',
  completed: 'bg-success/10 text-success',
  do_not_call: 'bg-destructive/10 text-destructive',
  invalid_number: 'bg-destructive/10 text-destructive',
}

export function ExecTaskStatusBadge({ status }: { status: OutboundTaskStatus }) {
  const { locale } = useLocaleStore()
  const localized = status === 'active' || status === 'paused'
  return (
    <span
      className={cn(
        'inline-flex shrink-0 rounded-md px-2 py-0.5 text-xs font-medium',
        execTaskStatusClass[status] ?? 'bg-muted text-muted-foreground',
      )}
    >
      {localized ? t(`ws.outboundExec.status.task.${status}`, locale) : OUTBOUND_TASK_STATUS_LABELS[status]}
    </span>
  )
}

export function ExecTargetStatusBadge({ status }: { status: OutboundTargetStatus }) {
  const { locale } = useLocaleStore()
  const key = `ws.outboundExec.status.target.${status}`
  const label = t(key, locale)
  return (
    <span className={cn('inline-flex shrink-0 rounded-md px-2 py-0.5 text-xs font-medium', execTargetStatusClass[status])}>
      {label === key ? OUTBOUND_TARGET_STATUS_LABELS[status] : label}
    </span>
  )
}
