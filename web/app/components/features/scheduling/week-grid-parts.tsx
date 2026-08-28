'use client'

import { useRef, useState, type CSSProperties, type ReactNode, type UIEvent } from 'react'
import { createPortal } from 'react-dom'
import { IconCalendarOff, IconX } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Assignment, Shift } from '@/models/scheduling'
import type { TargetBand } from '@/models/scheduling-rule'
import {
  gridTemplateColumns,
  monthDayLabel,
  summarizeDay,
  todayStr,
  weekdayLabel,
  type DaySummary,
} from './board-utils'

/** Immediate hover tip (no native title delay). Portaled to avoid overflow clipping. */
function InstantTip({
  tip,
  children,
  className,
  style,
}: {
  tip?: string
  children: ReactNode
  className?: string
  style?: CSSProperties
}) {
  const triggerRef = useRef<HTMLSpanElement>(null)
  const [pos, setPos] = useState<{ left: number; top: number; place: 'above' | 'below' } | null>(
    null,
  )

  if (!tip) {
    return (
      <span className={className} style={style}>
        {children}
      </span>
    )
  }

  const show = () => {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    const maxWidth = 220
    const margin = 8
    const place: 'above' | 'below' = rect.top > 96 ? 'above' : 'below'
    const left = Math.min(
      Math.max(rect.left + rect.width / 2 - maxWidth / 2, margin),
      window.innerWidth - maxWidth - margin,
    )
    setPos({
      left,
      top: place === 'above' ? rect.top - 6 : rect.bottom + 6,
      place,
    })
  }

  return (
    <>
      <span
        ref={triggerRef}
        className={className}
        style={style}
        onMouseEnter={show}
        onMouseLeave={() => setPos(null)}
      >
        {children}
      </span>
      {pos &&
        createPortal(
          <span
            role="tooltip"
            className="pointer-events-none fixed z-[100] max-w-[220px] rounded-md border border-border bg-popover px-2 py-1.5 text-left text-xs leading-5 text-popover-foreground shadow-md"
            style={{
              left: pos.left,
              top: pos.top,
              transform: pos.place === 'above' ? 'translateY(-100%)' : undefined,
            }}
          >
            {tip}
          </span>,
          document.body,
        )}
    </>
  )
}

/** Date header (top) and daily summary (bottom) stay pinned; only the body scrolls. Horizontal scroll stays in sync. */
export function WeekGridShell({
  minWidth,
  header,
  footer,
  children,
}: {
  minWidth: number
  header: ReactNode
  footer?: ReactNode
  children: ReactNode
}) {
  const headerRef = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const footerRef = useRef<HTMLDivElement>(null)
  const syncing = useRef(false)

  const syncScroll = (e: UIEvent<HTMLDivElement>) => {
    if (syncing.current) return
    const left = e.currentTarget.scrollLeft
    const targets = [headerRef.current, bodyRef.current, footerRef.current]
    syncing.current = true
    for (const el of targets) {
      if (el && el !== e.currentTarget) el.scrollLeft = left
    }
    requestAnimationFrame(() => {
      syncing.current = false
    })
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <div
        ref={headerRef}
        className="shrink-0 overflow-x-auto overflow-y-hidden bg-muted [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        onScroll={syncScroll}
      >
        <div style={{ minWidth }}>{header}</div>
      </div>
      <div
        ref={bodyRef}
        className="min-h-0 flex-1 overflow-auto"
        onScroll={syncScroll}
      >
        <div style={{ minWidth }}>{children}</div>
      </div>
      {footer != null && (
        <div
          ref={footerRef}
          className="shrink-0 overflow-x-auto overflow-y-hidden bg-muted [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          onScroll={syncScroll}
        >
          <div style={{ minWidth }}>{footer}</div>
        </div>
      )}
    </div>
  )
}

export function DayHeaderRow({ corner, weekDates }: { corner: string; weekDates: string[] }) {
  const { locale } = useLocaleStore()
  const today = todayStr()
  return (
    <div
      className="grid border-b border-border bg-muted"
      style={{ gridTemplateColumns: gridTemplateColumns(weekDates.length) }}
    >
      <div className="sticky left-0 z-10 border-r border-border bg-muted px-3 py-2.5 text-xs font-medium text-muted-foreground">
        {corner}
      </div>
      {weekDates.map((date) => {
        const isToday = date === today
        return (
          <div
            key={date}
            className={`border-r border-border px-2 py-2.5 text-center last:border-r-0 ${
              isToday ? 'bg-primary/5' : ''
            }`}
          >
            <div className="text-xs font-semibold">{weekdayLabel(date, locale)}</div>
            <div
              className={`text-[11px] ${isToday ? 'font-medium text-primary' : 'text-muted-foreground'}`}
            >
              {monthDayLabel(date)}
              {isToday ? ` · ${t('scheduling.board.today', locale)}` : ''}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function DailySummaryRow({
  weekDates,
  assignments,
  enabledShifts,
  targets,
}: {
  weekDates: string[]
  assignments: Assignment[]
  enabledShifts: Shift[]
  /** Rule-set target bands; null keeps the legacy empty/full badges. */
  targets?: Record<string, TargetBand> | null
}) {
  const { locale } = useLocaleStore()
  const today = todayStr()
  const byDate = new Map<string, Assignment[]>()
  for (const a of assignments) {
    const list = byDate.get(a.date)
    if (list) list.push(a)
    else byDate.set(a.date, [a])
  }
  return (
    <div
      className="grid border-t border-border bg-muted"
      style={{ gridTemplateColumns: gridTemplateColumns(weekDates.length) }}
    >
      <div className="sticky left-0 z-10 flex items-center border-r border-border bg-muted px-3 py-2.5 text-xs font-semibold text-muted-foreground">
        {t('scheduling.board.dailySummary', locale)}
      </div>
      {weekDates.map((date) => {
        const s: DaySummary = summarizeDay(byDate.get(date) ?? [], enabledShifts, targets, date)
        return (
          <div
            key={date}
            className={`border-r border-border px-2 py-2 last:border-r-0 ${
              date === today ? 'bg-primary/5' : ''
            }`}
          >
            <InstantTip
              className="block text-[11px] font-semibold tabular-nums"
              tip={t('scheduling.board.summary.peopleTip', locale)}
            >
              {t('scheduling.board.summary.people', locale, {
                headcount: s.headcount,
                slots: s.slots,
              })}
            </InstantTip>
            <div className="mt-1 flex flex-wrap gap-1">
              {s.byShift.map((x) => {
                const target = x.target != null && x.target > 0 ? x.target : null
                return (
                  <ShiftCountTag
                    key={x.shift.id}
                    name={x.shift.name}
                    color={x.shift.color}
                    count={target != null ? `${x.count}/${target}` : x.count}
                    tip={
                      target != null
                        ? t('scheduling.board.summary.shiftWithTargetTip', locale, {
                            name: x.shift.name,
                            count: x.count,
                            target,
                          })
                        : t('scheduling.board.summary.shiftCountTip', locale, {
                            name: x.shift.name,
                            count: x.count,
                          })
                    }
                  />
                )
              })}
            </div>
            {s.leaveHeadcount > 0 && (
              <div className="mt-1 flex flex-wrap items-center gap-1">
                <InstantTip
                  className="inline-flex items-center gap-0.5 rounded bg-violet-50 px-1 py-px text-[10px] text-violet-700"
                  tip={t('scheduling.board.summary.leaveTip', locale)}
                >
                  <IconCalendarOff size={10} />
                  {t('scheduling.board.summary.leave', locale, { count: s.leaveHeadcount })}
                </InstantTip>
                {s.byLeave.map((item) => (
                  <ShiftCountTag
                    key={item.shift.id}
                    name={item.shift.name}
                    color={item.shift.color}
                    count={item.count}
                  />
                ))}
              </div>
            )}
            <div className="mt-1 flex flex-wrap gap-1">
              {s.gap != null && s.overflow != null ? (
                <>
                  {s.gap > 0 && (
                    <InstantTip
                      className="rounded bg-amber-50 px-1 py-px text-[10px] text-amber-800"
                      tip={t('scheduling.board.summary.gapTip', locale)}
                    >
                      {t('scheduling.board.summary.gap', locale, { count: s.gap })}
                    </InstantTip>
                  )}
                  {s.overflow > 0 && (
                    <InstantTip
                      className="rounded bg-muted px-1 py-px text-[10px] text-muted-foreground"
                      tip={t('scheduling.board.summary.overflowTip', locale)}
                    >
                      {t('scheduling.board.summary.overflow', locale, { count: s.overflow })}
                    </InstantTip>
                  )}
                  {s.gap === 0 && s.overflow === 0 && (
                    <InstantTip
                      className="rounded bg-emerald-50 px-1 py-px text-[10px] text-emerald-700"
                      tip={t('scheduling.board.summary.onTargetTip', locale)}
                    >
                      {t('scheduling.board.summary.onTarget', locale)}
                    </InstantTip>
                  )}
                </>
              ) : s.emptyShifts > 0 ? (
                <InstantTip
                  className="rounded bg-red-50 px-1 py-px text-[10px] text-red-700"
                  tip={t('scheduling.board.summary.emptyTip', locale, {
                    count: s.emptyShifts,
                  })}
                >
                  {t('scheduling.board.summary.empty', locale, { count: s.emptyShifts })}
                </InstantTip>
              ) : (
                <InstantTip
                  className="rounded bg-emerald-50 px-1 py-px text-[10px] text-emerald-700"
                  tip={t('scheduling.board.summary.fullTip', locale)}
                >
                  {t('scheduling.board.summary.full', locale)}
                </InstantTip>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export function CellViolationBadge({
  level,
  title,
}: {
  level: 'hard' | 'soft'
  title: string
}) {
  return (
    <span
      title={title}
      className={`absolute right-1 top-1 z-10 h-2 w-2 rounded-full ${
        level === 'hard' ? 'bg-red-500' : 'bg-amber-500'
      }`}
    />
  )
}

export function AgentChip({
  name,
  stale,
  onRemove,
}: {
  name: string
  /** Employee left the pool: dashed muted chip, still removable. */
  stale?: boolean
  onRemove?: () => void
}) {
  const { locale } = useLocaleStore()
  return (
    <span
      className={`group inline-flex max-w-full items-center gap-0.5 rounded-md border px-1.5 py-0.5 text-[11px] leading-4 ${
        stale
          ? 'border-dashed border-border bg-muted/30 text-muted-foreground'
          : 'border-border bg-white'
      }`}
      title={stale ? t('scheduling.board.notInPool', locale) : undefined}
    >
      <span className="truncate">{name}</span>
      {onRemove && (
        <button
          type="button"
          aria-label="Remove"
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          className="hidden shrink-0 text-muted-foreground hover:text-foreground group-hover:inline-flex"
        >
          <IconX size={11} />
        </button>
      )}
    </span>
  )
}

/** Outline count badge for period/daily stats (border + shift color text). */
export function ShiftCountTag({
  name,
  color,
  count,
  tip,
}: {
  name: string
  color: string
  count: string | number
  tip?: string
}) {
  return (
    <InstantTip
      className="rounded border px-1 py-px text-[10px] font-medium"
      style={{ borderColor: color, color }}
      tip={tip}
    >
      {name}
      {count}
    </InstantTip>
  )
}

/** Agent×day cell: fixed-width tall solid-color card (width < height). */
export function ShiftChip({
  shift,
  onRemove,
}: {
  shift: { name: string; color: string; shift_type?: 'work' | 'leave' }
  onRemove?: () => void
}) {
  const isLeave = shift.shift_type === 'leave'
  return (
    <span
      className={`group relative flex shrink-0 items-center justify-center rounded-md px-1 text-[11px] font-medium leading-4 text-white ${
        isLeave ? 'h-8 min-w-14 gap-1' : 'h-14 w-10'
      }`}
      style={{ background: shift.color }}
      title={shift.name}
    >
      {isLeave && <IconCalendarOff size={13} className="shrink-0" />}
      <span className="truncate">{shift.name}</span>
      {onRemove && (
        <button
          type="button"
          aria-label="Remove"
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          className="absolute right-0 top-0 hidden rounded-bl bg-black/20 p-0.5 text-white/90 hover:bg-black/35 hover:text-white group-hover:inline-flex"
        >
          <IconX size={11} />
        </button>
      )}
    </span>
  )
}
