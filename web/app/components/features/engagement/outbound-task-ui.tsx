'use client'

import {
  OUTBOUND_TARGET_STATUS_LABELS,
  OUTBOUND_TASK_STATUS_LABELS,
  type OutboundTargetStatus,
  type OutboundTaskStatus,
} from '@/models/outbound-task'
import { cn } from '@/lib/utils'

const taskStatusClass: Record<OutboundTaskStatus, string> = {
  draft: 'bg-muted text-muted-foreground',
  active: 'bg-success/10 text-success',
  paused: 'bg-warning/10 text-warning',
  completed: 'bg-info/10 text-info',
  archived: 'bg-secondary text-muted-foreground',
}

const targetStatusClass: Record<OutboundTargetStatus, string> = {
  pending: 'bg-muted text-muted-foreground',
  calling: 'bg-info/10 text-info',
  redial: 'bg-warning/10 text-warning',
  completed: 'bg-success/10 text-success',
  do_not_call: 'bg-destructive/10 text-destructive',
  invalid_number: 'bg-destructive/10 text-destructive',
}

export function TaskStatusBadge({ status }: { status: OutboundTaskStatus }) {
  return (
    <span className={cn('inline-flex rounded-md px-2 py-1 text-xs font-medium', taskStatusClass[status])}>
      {OUTBOUND_TASK_STATUS_LABELS[status]}
    </span>
  )
}

export function TargetStatusBadge({ status }: { status: OutboundTargetStatus }) {
  return (
    <span className={cn('inline-flex rounded-md px-2 py-1 text-xs font-medium', targetStatusClass[status])}>
      {OUTBOUND_TARGET_STATUS_LABELS[status]}
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

export function EmptyState({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border bg-muted/20 text-center">
      <p className="text-sm font-medium text-foreground">{title}</p>
      {action}
    </div>
  )
}
