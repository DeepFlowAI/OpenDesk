'use client'

import { IconCalendarOff, IconPlus, IconX } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Assignment, Shift } from '@/models/scheduling'
import {
  calendarCells,
  monthDayLabel,
  summarizeDay,
  todayStr,
  weekdayLabel,
} from './board-utils'
import { AgentChip } from './week-grid-parts'

export type CalendarViewProps = {
  month: string
  selectedDay: string | null
  shifts: Shift[]
  assignments: Assignment[]
  poolIds: Set<number>
  onSelectDay: (date: string | null) => void
  onAddAgents: (shift: Shift, date: string) => void
  onRemove: (assignment: Assignment) => void
}

export function CalendarView({
  month,
  selectedDay,
  shifts,
  assignments,
  poolIds,
  onSelectDay,
  onAddAgents,
  onRemove,
}: CalendarViewProps) {
  const { locale } = useLocaleStore()
  const today = todayStr()
  const cells = calendarCells(month)
  const byDate = new Map<string, Assignment[]>()
  for (const a of assignments) {
    const list = byDate.get(a.date)
    if (list) list.push(a)
    else byDate.set(a.date, [a])
  }

  const selectedAssignments = selectedDay ? (byDate.get(selectedDay) ?? []) : []
  const selectedSummary = selectedDay ? summarizeDay(selectedAssignments, shifts) : null
  const orderedShifts = [
    ...shifts.filter((shift) => (shift.shift_type ?? 'work') === 'work'),
    ...shifts.filter((shift) => shift.shift_type === 'leave'),
  ]

  return (
    <div className="flex min-h-0 flex-1">
      <div className="min-h-0 min-w-0 flex-1 overflow-auto p-4">
        <div className="mb-2 grid grid-cols-7 gap-px">
          {[1, 2, 3, 4, 5, 6, 0].map((w) => (
            <div
              key={w}
              className="px-2 py-1.5 text-center text-xs font-medium text-muted-foreground"
            >
              {t(`scheduling.board.weekday.${w}`, locale)}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-px overflow-hidden rounded-xl border border-border bg-border">
          {cells.map((cell) => {
            const dayList = byDate.get(cell.date) ?? []
            const counts = orderedShifts.map((shift) => ({
              shift,
              count: dayList.filter((a) => a.shift.id === shift.id).length,
            }))
            const hasData = counts.some((c) => c.count > 0)
            const selected = selectedDay === cell.date
            return (
              <div
                key={cell.date}
                role="button"
                tabIndex={0}
                onClick={() => onSelectDay(cell.date)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onSelectDay(cell.date)
                  }
                }}
                className={`min-h-[100px] cursor-pointer bg-white p-2 ${
                  cell.outside ? 'bg-muted/30' : ''
                } ${cell.isToday && !selected ? 'ring-2 ring-inset ring-primary/30' : ''} ${
                  selected ? 'ring-2 ring-inset ring-primary bg-primary/[0.04]' : ''
                }`}
              >
                <div
                  className={`mb-1.5 text-xs font-semibold tabular-nums ${
                    cell.outside
                      ? 'text-muted-foreground/50'
                      : selected || cell.isToday
                        ? 'text-primary'
                        : 'text-foreground'
                  }`}
                >
                  {cell.dayNum}
                  {cell.isToday && (
                    <span className="ml-1 text-[10px] font-medium">
                      {t('scheduling.board.today', locale)}
                    </span>
                  )}
                </div>
                {cell.outside ? null : hasData ? (
                  <div className="space-y-1">
                    {counts
                      .filter(({ shift, count }) => shift.shift_type !== 'leave' || count > 0)
                      .map(({ shift, count }) =>
                      count === 0 ? (
                        <div
                          key={shift.id}
                          className="flex items-center justify-between rounded px-1.5 py-0.5 text-[10px] text-muted-foreground/50"
                        >
                          <span>{shift.name}</span>
                          <span>0</span>
                        </div>
                      ) : (
                        <div
                          key={shift.id}
                          className="flex items-center justify-between rounded px-1.5 py-0.5 text-[10px] font-medium text-white"
                          style={{ background: shift.color }}
                        >
                          <span className="inline-flex min-w-0 items-center gap-0.5 truncate">
                            {shift.shift_type === 'leave' && <IconCalendarOff size={10} />}
                            {shift.name}
                          </span>
                          <span className="tabular-nums">{count}</span>
                        </div>
                      ),
                    )}
                  </div>
                ) : (
                  <div className="text-[10px] text-muted-foreground/60">
                    {t('scheduling.board.calendar.unassigned', locale)}
                  </div>
                )}
              </div>
            )
          })}
        </div>
        {!selectedDay && (
          <p className="mt-3 text-center text-[11px] text-muted-foreground">
            {t('scheduling.board.calendar.pickHint', locale)}
          </p>
        )}
      </div>

      {selectedDay && selectedSummary && (
        <aside className="flex w-[340px] shrink-0 flex-col border-l border-border bg-white">
          <div className="flex items-start justify-between border-b border-border px-4 py-3">
            <div>
              <h2 className="text-sm font-semibold">
                {weekdayLabel(selectedDay, locale)} {monthDayLabel(selectedDay)}
                {selectedDay === today && (
                  <span className="ml-1.5 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                    {t('scheduling.board.today', locale)}
                  </span>
                )}
              </h2>
              <p className="mt-1 text-[11px] text-muted-foreground">
                {t('scheduling.board.calendar.summaryLine', locale, {
                  headcount: selectedSummary.headcount,
                  slots: selectedSummary.slots,
                })}
                {selectedSummary.emptyShifts > 0
                  ? ` · ${t('scheduling.board.calendar.emptyShifts', locale, { count: selectedSummary.emptyShifts })}`
                  : ` · ${t('scheduling.board.calendar.full', locale)}`}
                {selectedSummary.leaveHeadcount > 0
                  ? ` · ${t('scheduling.board.summary.leave', locale, { count: selectedSummary.leaveHeadcount })}`
                  : ''}
              </p>
            </div>
            <button
              type="button"
              onClick={() => onSelectDay(null)}
              className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground hover:bg-muted"
              aria-label={t('scheduling.board.calendar.close', locale)}
            >
              <IconX size={16} />
            </button>
          </div>

          <div className="min-h-0 flex-1 space-y-3 overflow-auto px-4 py-3">
            {orderedShifts.map((shift) => {
              const cell = selectedAssignments.filter((a) => a.shift.id === shift.id)
              return (
                <div key={shift.id} className="overflow-hidden rounded-lg border border-border">
                  <div
                    className="flex items-center justify-between px-3 py-2 text-white"
                    style={{ background: shift.color }}
                  >
                    <div>
                      <div className="flex items-center gap-1 text-sm font-semibold">
                        {shift.shift_type === 'leave' && <IconCalendarOff size={14} />}
                        {shift.name}
                      </div>
                      <div className="text-[11px] text-white/85 tabular-nums">
                        {shift.shift_type === 'leave'
                          ? t('scheduling.shifts.allDay', locale)
                          : `${shift.start_time}–${shift.end_time}`}
                      </div>
                    </div>
                    <span className="text-xs font-medium tabular-nums">
                      {t('scheduling.board.calendar.peopleCount', locale, { count: cell.length })}
                    </span>
                  </div>
                  <div className="space-y-2 bg-white px-3 py-2.5">
                    {cell.length === 0 ? (
                      <div className="rounded-md border border-dashed border-border px-2 py-3 text-center text-[11px] text-muted-foreground">
                        {t('scheduling.board.calendar.noAgents', locale)}
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-1.5">
                        {cell.map((a) => (
                          <AgentChip
                            key={a.id}
                            name={a.employee.name}
                            stale={!poolIds.has(a.employee.id)}
                            onRemove={() => onRemove(a)}
                          />
                        ))}
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => onAddAgents(shift, selectedDay)}
                      disabled={!shift.is_enabled}
                      className="inline-flex h-8 w-full items-center justify-center gap-1 rounded-md border border-border text-xs font-medium hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <IconPlus size={14} />
                      {shift.is_enabled
                        ? t('scheduling.board.calendar.addAgents', locale)
                        : t('scheduling.shifts.disabled', locale)}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </aside>
      )}
    </div>
  )
}
