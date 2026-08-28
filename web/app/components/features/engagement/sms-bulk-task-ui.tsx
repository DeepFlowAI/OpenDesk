'use client'

import {
  SMS_BULK_TARGET_STATUS_LABELS,
  SMS_BULK_TASK_STATUS_LABELS,
  type SmsBulkTargetStatus,
  type SmsBulkTaskStatus,
} from '@/models/sms-bulk-task'
import { cn } from '@/lib/utils'

const taskStatusClass: Record<SmsBulkTaskStatus, string> = {
  draft: 'bg-muted text-muted-foreground',
  scheduled: 'bg-info/10 text-info',
  sending: 'bg-success/10 text-success',
  paused: 'bg-warning/10 text-warning',
  completed: 'bg-info/10 text-info',
  archived: 'bg-secondary text-muted-foreground',
}

const targetStatusClass: Record<SmsBulkTargetStatus, string> = {
  pending: 'bg-muted text-muted-foreground',
  sending: 'bg-info/10 text-info',
  submitted: 'bg-info/10 text-info',
  delivered: 'bg-success/10 text-success',
  failed: 'bg-destructive/10 text-destructive',
}

export function SmsTaskStatusBadge({ status }: { status: SmsBulkTaskStatus }) {
  return (
    <span className={cn('inline-flex rounded-md px-2 py-1 text-xs font-medium', taskStatusClass[status])}>
      {SMS_BULK_TASK_STATUS_LABELS[status]}
    </span>
  )
}

export function SmsTargetStatusBadge({ status }: { status: SmsBulkTargetStatus }) {
  return (
    <span className={cn('inline-flex rounded-md px-2 py-1 text-xs font-medium', targetStatusClass[status])}>
      {SMS_BULK_TARGET_STATUS_LABELS[status]}
    </span>
  )
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatPercent(numerator: number, denominator: number): string {
  if (!denominator) return '-'
  return `${Math.round((numerator / denominator) * 100)}%`
}

/** Render an SMS body with {variable} placeholders highlighted or replaced. */
export function renderSmsBody(body: string, values?: Record<string, string>): React.ReactNode[] {
  return body.split(/(\{[^}]+\})/g).map((part, i) => {
    const match = part.match(/^\{([^}]+)\}$/)
    if (!match) return part
    const key = match[1]
    const value = values?.[key]
    return (
      <span key={i} className="rounded bg-primary/10 px-1 font-medium text-primary">
        {value || part}
      </span>
    )
  })
}

export function EmptyState({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-muted/20 text-center">
      <p className="text-sm font-medium text-foreground">{title}</p>
      {action}
    </div>
  )
}
