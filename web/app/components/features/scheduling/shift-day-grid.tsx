'use client'

import { Fragment } from 'react'
import { IconCalendarOff, IconPlus } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Assignment, Shift } from '@/models/scheduling'
import type { RuleViolation, TargetBand } from '@/models/scheduling-rule'
import { assignmentsByCell, gridMinWidth, gridTemplateColumns, todayStr } from './board-utils'
import { cellLevel, violationText } from './violation-utils'
import {
  AgentChip,
  CellViolationBadge,
  DailySummaryRow,
  DayHeaderRow,
  WeekGridShell,
} from './week-grid-parts'

export type ShiftDayGridProps = {
  weekDates: string[]
  shifts: Shift[]
  assignments: Assignment[]
  poolIds: Set<number>
  multiMode: boolean
  selectedCells: Set<string>
  onCellClick: (shift: Shift, date: string) => void
  onRemove: (assignment: Assignment) => void
  /** Violations per "shiftId:date" cell; badges + optional filtering. */
  violationCells?: Map<string, RuleViolation[]>
  /** ?violations=1: dim cells without violations. */
  violationsOnly?: boolean
  /** Rule-set target bands for the summary row. */
  targets?: Record<string, TargetBand> | null
}

export function ShiftDayGrid({
  weekDates,
  shifts,
  assignments,
  poolIds,
  multiMode,
  selectedCells,
  onCellClick,
  onRemove,
  violationCells,
  violationsOnly = false,
  targets,
}: ShiftDayGridProps) {
  const { locale } = useLocaleStore()
  const today = todayStr()
  const byCell = assignmentsByCell(assignments)
  const columns = gridTemplateColumns(weekDates.length)
  const minWidth = gridMinWidth(weekDates.length)
  const orderedShifts = [
    ...shifts.filter((shift) => (shift.shift_type ?? 'work') === 'work'),
    ...shifts.filter((shift) => shift.shift_type === 'leave'),
  ]
  const firstLeaveId = orderedShifts.find((shift) => shift.shift_type === 'leave')?.id

  return (
    <WeekGridShell
      minWidth={minWidth}
      header={
        <DayHeaderRow corner={t('scheduling.board.corner.shiftDay', locale)} weekDates={weekDates} />
      }
      footer={
        <DailySummaryRow
          weekDates={weekDates}
          assignments={assignments}
          enabledShifts={shifts}
          targets={targets}
        />
      }
    >
      {orderedShifts.map((shift) => (
        <Fragment key={shift.id}>
          {shift.id === firstLeaveId && (
            <div className="border-b border-border bg-muted/60 px-3 py-1.5 text-[11px] font-medium text-muted-foreground">
              <span className="inline-flex items-center gap-1">
                <IconCalendarOff size={13} />
                {t('scheduling.shiftType.leave', locale)}
              </span>
            </div>
          )}
          <div
            className="grid border-b border-border"
            style={{ gridTemplateColumns: columns }}
          >
          <div className="sticky left-0 z-10 border-r border-border bg-white p-2">
            <div className="rounded-md px-2.5 py-2 text-white" style={{ background: shift.color }}>
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
          </div>
          {weekDates.map((date) => {
            const cellKey = `${shift.id}:${date}`
            const cell = byCell.get(cellKey) ?? []
            const empty = cell.length === 0
            const selected = selectedCells.has(cellKey)
            const cellViolationList = violationCells?.get(cellKey)
            const level = cellLevel(cellViolationList)
            const dimmed = violationsOnly && !level
            return (
              <div
                key={date}
                role="button"
                tabIndex={0}
                onClick={() => onCellClick(shift, date)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    onCellClick(shift, date)
                  }
                }}
                className={`relative min-h-[88px] border-r border-border p-1.5 last:border-r-0 ${
                  shift.is_enabled || multiMode ? 'cursor-pointer' : 'cursor-default'
                } ${
                  date === today ? 'bg-primary/[0.03]' : 'bg-white'
                } ${selected ? 'bg-primary/10 ring-2 ring-inset ring-primary' : ''} ${
                  level === 'hard'
                    ? 'ring-1 ring-inset ring-red-300'
                    : level === 'soft'
                      ? 'ring-1 ring-inset ring-amber-300'
                      : ''
                } ${dimmed ? 'opacity-40' : ''}`}
              >
                {level && cellViolationList && (
                  <CellViolationBadge
                    level={level}
                    title={cellViolationList.map((v) => violationText(v, locale)).join('\n')}
                  />
                )}
                {empty ? (
                  <div className="flex min-h-[76px] items-center justify-center rounded-md border border-dashed border-border/80 text-[11px] text-muted-foreground">
                    {shift.is_enabled ? (
                      <span className="inline-flex items-center gap-0.5">
                        <IconPlus size={12} />
                        {t('scheduling.board.add', locale)}
                      </span>
                    ) : (
                      t('scheduling.shifts.disabled', locale)
                    )}
                  </div>
                ) : (
                  <div className="flex flex-wrap items-start gap-1">
                    {cell.map((a) => (
                      <AgentChip
                        key={a.id}
                        name={a.employee.name}
                        stale={!poolIds.has(a.employee.id)}
                        onRemove={multiMode ? undefined : () => onRemove(a)}
                      />
                    ))}
                  </div>
                )}
              </div>
            )
          })}
          </div>
        </Fragment>
      ))}
    </WeekGridShell>
  )
}
