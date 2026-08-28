'use client'

import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Assignment, PoolMember, Shift } from '@/models/scheduling'
import type { RuleViolation, TargetBand } from '@/models/scheduling-rule'
import {
  agentPeriodShiftCounts,
  assignmentsByAgentCell,
  gridMinWidth,
  gridTemplateColumns,
  todayStr,
} from './board-utils'
import { cellLevel, violationText } from './violation-utils'
import {
  CellViolationBadge,
  DailySummaryRow,
  DayHeaderRow,
  ShiftChip,
  ShiftCountTag,
  WeekGridShell,
} from './week-grid-parts'

function compareShiftTime(
  a: { start_time: string; sort_order?: number; shift_type?: 'work' | 'leave' },
  b: { start_time: string; sort_order?: number; shift_type?: 'work' | 'leave' },
) {
  if ((a.shift_type ?? 'work') !== (b.shift_type ?? 'work')) {
    return a.shift_type === 'leave' ? 1 : -1
  }
  if (a.start_time !== b.start_time) return a.start_time.localeCompare(b.start_time)
  return (a.sort_order ?? 0) - (b.sort_order ?? 0)
}

export type AgentDayGridProps = {
  weekDates: string[]
  shifts: Shift[]
  assignments: Assignment[]
  pool: PoolMember[]
  multiMode: boolean
  selectedCells: Set<string>
  onCellClick: (member: PoolMember, date: string) => void
  onRemove: (assignment: Assignment) => void
  /** Violations per "employeeId:date" cell; badges + optional filtering. */
  violationCells?: Map<string, RuleViolation[]>
  /** ?violations=1: dim cells without violations. */
  violationsOnly?: boolean
  /** Rule-set target bands for the summary row. */
  targets?: Record<string, TargetBand> | null
}

export function AgentDayGrid({
  weekDates,
  shifts,
  assignments,
  pool,
  multiMode,
  selectedCells,
  onCellClick,
  onRemove,
  violationCells,
  violationsOnly = false,
  targets,
}: AgentDayGridProps) {
  const { locale } = useLocaleStore()
  const today = todayStr()
  const byCell = assignmentsByAgentCell(assignments)
  const periodCounts = agentPeriodShiftCounts(assignments, shifts)
  const columns = gridTemplateColumns(weekDates.length)
  const minWidth = gridMinWidth(weekDates.length)

  return (
    <WeekGridShell
      minWidth={minWidth}
      header={
        <DayHeaderRow corner={t('scheduling.board.corner.agentDay', locale)} weekDates={weekDates} />
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
      {pool.map((member) => {
        const shiftStats = periodCounts.get(member.id) ?? []
        return (
          <div
            key={member.id}
            className="grid border-b border-border"
            style={{ gridTemplateColumns: columns }}
          >
            <div className="sticky left-0 z-10 flex items-center gap-2 border-r border-border bg-white px-3 py-3">
              <div className="min-w-0">
                <div className="truncate text-sm font-medium">{member.name}</div>
                {member.job_number && (
                  <div className="font-mono text-[11px] text-muted-foreground">
                    {member.job_number}
                  </div>
                )}
                {shiftStats.length > 0 && (
                  <div className="mt-1 flex flex-wrap gap-1">
                    {shiftStats.map(({ shift, count }) => (
                      <ShiftCountTag
                        key={shift.id}
                        name={shift.name}
                        color={shift.color}
                        count={count}
                        tip={t('scheduling.board.summary.shiftCountTip', locale, {
                          name: shift.name,
                          count,
                        })}
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
            {weekDates.map((date) => {
              const cellKey = `${member.id}:${date}`
              const cell = (byCell.get(cellKey) ?? [])
                .slice()
                .sort((a, b) => compareShiftTime(a.shift, b.shift))
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
                  onClick={() => onCellClick(member, date)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      onCellClick(member, date)
                    }
                  }}
                  className={`relative flex min-h-[72px] cursor-pointer flex-col border-r border-border p-1.5 last:border-r-0 ${
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
                    <div className="flex min-h-[60px] items-center justify-center rounded-md border border-dashed border-border/80 text-[11px] text-muted-foreground">
                      {t('scheduling.board.assign', locale)}
                    </div>
                  ) : (
                    <div className="flex flex-wrap content-start justify-start gap-1">
                      {cell.map((a) => (
                        <ShiftChip
                          key={a.id}
                          shift={a.shift}
                          onRemove={multiMode ? undefined : () => onRemove(a)}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )
      })}
    </WeekGridShell>
  )
}
