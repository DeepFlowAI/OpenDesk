'use client'

import type { Locale } from '@/context/locale-store'
import type {
  AutoOutboundExecutionMode,
  AutoOutboundReceptionType,
  AutoOutboundTargetStatus,
  AutoOutboundTaskStatus,
  AutoOutboundTerminalState,
} from '@/models/auto-outbound-task'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'

const taskStatusClass: Record<AutoOutboundTaskStatus, string> = {
  draft: 'bg-muted text-muted-foreground',
  active: 'bg-success/10 text-success',
  paused: 'bg-warning/10 text-warning',
  completed: 'bg-info/10 text-info',
  archived: 'bg-secondary text-muted-foreground',
}

const modeClass: Record<AutoOutboundExecutionMode, string> = {
  ivr: 'bg-info/10 text-info',
  bot: 'bg-secondary text-foreground',
  agent: 'bg-success/10 text-success',
}

const targetStatusClass: Record<AutoOutboundTargetStatus, string> = {
  pending: 'bg-muted text-muted-foreground',
  calling: 'bg-info/10 text-info',
  redial_pending: 'bg-warning/10 text-warning',
  completed: 'bg-success/10 text-success',
  invalid: 'bg-destructive/10 text-destructive',
}

const terminalStateClass: Record<AutoOutboundTerminalState, string> = {
  answered: 'bg-success/10 text-success',
  no_answer: 'bg-warning/10 text-warning',
  busy: 'bg-warning/10 text-warning',
  power_off: 'bg-warning/10 text-warning',
  invalid_number: 'bg-destructive/10 text-destructive',
  failed: 'bg-destructive/10 text-destructive',
}

const AUTO_PAUSE_REASON_CODES = ['dial_service_unavailable', 'queue_finished'] as const

export function localizedAutoPauseReason(reason: string, locale: Locale): string {
  // Known codes map to localized copy; legacy free-form copy renders as-is.
  return (AUTO_PAUSE_REASON_CODES as readonly string[]).includes(reason)
    ? t(`ws.autoOutbound.autoPauseReason.${reason}`, locale)
    : reason
}

export function AutoTaskStatusBadge({
  status,
  outOfWindow,
  autoPauseReason,
  locale,
}: {
  status: AutoOutboundTaskStatus
  outOfWindow?: boolean
  autoPauseReason?: string | null
  locale: Locale
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className={cn('inline-flex rounded-md px-2 py-1 text-xs font-medium', taskStatusClass[status])}>
        {t(`ws.autoOutbound.status.${status}`, locale)}
      </span>
      {status === 'active' && outOfWindow ? (
        <span className="rounded-md border border-warning/40 bg-warning/10 px-1.5 py-0.5 text-[10px] text-warning">
          {t('ws.autoOutbound.status.waitingWindow', locale)}
        </span>
      ) : null}
      {status === 'paused' && autoPauseReason === 'queue_finished' ? (
        <span className="rounded-md border border-border bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
          {t('ws.autoOutbound.status.queueFinished', locale)}
        </span>
      ) : null}
    </div>
  )
}

export function ExecutionModeBadge({
  mode,
  locale,
}: {
  mode: AutoOutboundExecutionMode
  locale: Locale
}) {
  return (
    <span className={cn('inline-flex rounded-md px-2 py-1 text-xs font-medium', modeClass[mode])}>
      {t(`ws.autoOutbound.mode.${mode}`, locale)}
    </span>
  )
}

export function AutoTargetStatusBadge({
  status,
  locale,
}: {
  status: AutoOutboundTargetStatus
  locale: Locale
}) {
  return (
    <span className={cn('inline-flex rounded-md px-2 py-1 text-xs font-medium', targetStatusClass[status])}>
      {t(`ws.autoOutbound.targetStatus.${status}`, locale)}
    </span>
  )
}

export function TerminalStateBadge({
  state,
  locale,
}: {
  state: AutoOutboundTerminalState
  locale: Locale
}) {
  return (
    <span className={cn('inline-flex rounded-md px-2 py-1 text-xs font-medium', terminalStateClass[state])}>
      {t(`ws.autoOutbound.terminal.${state}`, locale)}
    </span>
  )
}

export function receptionTypeLabel(
  type: AutoOutboundReceptionType,
  agentName: string | null | undefined,
  locale: Locale,
): string {
  if (type === 'agent') {
    return agentName
      ? t('ws.autoOutbound.reception.agentWithName', locale, { name: agentName })
      : t('ws.autoOutbound.reception.agent', locale)
  }
  return t(`ws.autoOutbound.reception.${type}`, locale)
}

export function ProgressBar({ finished, total }: { finished: number; total: number }) {
  const pct = total > 0 ? Math.min(100, Math.round((finished / total) * 100)) : 0
  return (
    <div>
      <div className="text-sm">
        {finished.toLocaleString()} / {total.toLocaleString()}
      </div>
      <div className="mt-1 h-1.5 w-24 overflow-hidden rounded-full bg-muted">
        <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

export function formatAnswerRate(
  rate: number | string | null | undefined,
  answered?: number,
  calls?: number,
): string {
  const n = rate == null || rate === '' ? null : Number(rate)
  if (n != null && Number.isFinite(n)) return `${Math.round(n * (n <= 1 ? 100 : 1))}%`
  if (calls != null && answered != null) {
    if (!calls) return '—'
    return `${Math.round((answered / calls) * 100)}%`
  }
  return '—'
}

export function SimplePagination({
  page,
  pageSize,
  total,
  locale,
  onPageChange,
}: {
  page: number
  pageSize: number
  total: number
  locale: Locale
  onPageChange: (page: number) => void
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize))
  if (total <= 0 || totalPages <= 1) return null
  return (
    <div className="mt-4 flex items-center justify-end gap-2 text-sm text-muted-foreground">
      <span>
        {page} / {totalPages}
      </span>
      <button
        type="button"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        className="h-8 rounded-md border border-border px-3 disabled:opacity-40"
      >
        {t('ws.autoOutbound.pagination.prev', locale)}
      </button>
      <button
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        className="h-8 rounded-md border border-border px-3 disabled:opacity-40"
      >
        {t('ws.autoOutbound.pagination.next', locale)}
      </button>
    </div>
  )
}

export function formatDateTime(value: string | null | undefined, withSeconds = false): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    ...(withSeconds ? { second: '2-digit' } : {}),
  })
}

export function formatDurationMs(ms: number | null | undefined): string {
  if (ms == null || ms < 0) return '—'
  const totalSec = Math.floor(ms / 1000)
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

export function TableSkeleton({ rows = 6, cols = 8 }: { rows?: number; cols?: number }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="animate-pulse">
        <div className="h-11 bg-muted/60" />
        {Array.from({ length: rows }).map((_, row) => (
          <div key={row} className="flex gap-4 border-t border-border px-4 py-4">
            {Array.from({ length: cols }).map((_, col) => (
              <div key={col} className="h-4 flex-1 rounded bg-muted/50" />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

export function MetricCard({
  label,
  value,
  danger,
  testId,
}: {
  label: string
  value: string | number
  danger?: boolean
  testId?: string
}) {
  return (
    <div className="rounded-lg border border-border p-4" data-testid={testId}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn('mt-2 text-2xl font-semibold', danger && 'text-destructive')}>{value}</p>
    </div>
  )
}

export function SimpleBarChart({
  items,
  emptyLabel,
}: {
  items: Array<{ label: string; value: number; accent?: boolean }>
  emptyLabel: string
}) {
  const max = Math.max(0, ...items.map((item) => item.value))
  if (items.length === 0 || max === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">{emptyLabel}</p>
  }
  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.label}>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span className="text-muted-foreground">{item.label}</span>
            <span className="font-medium">{item.value.toLocaleString()}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className={cn('h-full rounded-full', item.accent ? 'bg-destructive' : 'bg-primary')}
              style={{ width: `${Math.round((item.value / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

export function DailyTrendBars({
  items,
  emptyLabel,
}: {
  items: Array<{ date: string; call_count: number; answered_count: number }>
  emptyLabel: string
}) {
  const max = Math.max(0, ...items.map((item) => item.call_count))
  if (items.length === 0 || max === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">{emptyLabel}</p>
  }
  return (
    <div className="flex h-40 items-end gap-2">
      {items.map((item) => {
        const callH = Math.max(4, Math.round((item.call_count / max) * 100))
        const ansH = item.call_count
          ? Math.max(2, Math.round((item.answered_count / item.call_count) * callH))
          : 0
        return (
          <div key={item.date} className="flex min-w-0 flex-1 flex-col items-center gap-1">
            <div className="relative flex h-28 w-full items-end justify-center">
              <div className="relative w-4 rounded-t bg-muted" style={{ height: `${callH}%` }}>
                <div
                  className="absolute bottom-0 left-0 right-0 rounded-t bg-primary"
                  style={{ height: `${ansH}%` }}
                />
              </div>
            </div>
            <span className="truncate text-[10px] text-muted-foreground">{item.date.slice(5)}</span>
          </div>
        )
      })}
    </div>
  )
}
