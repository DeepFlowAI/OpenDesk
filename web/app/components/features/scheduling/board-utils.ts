import type { Assignment, Shift } from '@/models/scheduling'
import type { TargetBand } from '@/models/scheduling-rule'

export type LayoutView = 'shift-day' | 'agent-day' | 'calendar'

export function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = `${d.getMonth() + 1}`.padStart(2, '0')
  const day = `${d.getDate()}`.padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function parseDate(s: string): Date {
  const [y, m, d] = s.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function todayStr(): string {
  return formatDate(new Date())
}

/** Monday of the week containing the given date. */
export function mondayOf(d: Date): Date {
  const day = d.getDay() // 0=Sun
  const diff = day === 0 ? -6 : 1 - day
  const monday = new Date(d.getFullYear(), d.getMonth(), d.getDate() + diff)
  return monday
}

export function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)
}

export function weekDates(weekStart: string): string[] {
  const monday = parseDate(weekStart)
  return Array.from({ length: 7 }, (_, i) => formatDate(addDays(monday, i)))
}

/** Inclusive day count between two YYYY-MM-DD dates. */
export function dayCount(start: string, end: string): number {
  return Math.floor((parseDate(end).getTime() - parseDate(start).getTime()) / 86_400_000) + 1
}

/** Inclusive list of YYYY-MM-DD dates from start through end. */
export function dateRange(start: string, end: string): string[] {
  const n = dayCount(start, end)
  if (n <= 0) return []
  const first = parseDate(start)
  return Array.from({ length: n }, (_, i) => formatDate(addDays(first, i)))
}

/** Max selectable span for board week views (backend allows 62). */
export const MAX_BOARD_RANGE_DAYS = 60

export type BoardRangePreset = 'thisWeek' | 'lastWeek' | 'thisMonth' | 'lastMonth'

export function boardRangePreset(key: BoardRangePreset, now = new Date()): { start: string; end: string } {
  if (key === 'thisWeek') {
    const start = mondayOf(now)
    return { start: formatDate(start), end: formatDate(addDays(start, 6)) }
  }
  if (key === 'lastWeek') {
    const start = addDays(mondayOf(now), -7)
    return { start: formatDate(start), end: formatDate(addDays(start, 6)) }
  }
  if (key === 'thisMonth') {
    const start = new Date(now.getFullYear(), now.getMonth(), 1)
    const end = new Date(now.getFullYear(), now.getMonth() + 1, 0)
    return { start: formatDate(start), end: formatDate(end) }
  }
  const start = new Date(now.getFullYear(), now.getMonth() - 1, 1)
  const end = new Date(now.getFullYear(), now.getMonth(), 0)
  return { start: formatDate(start), end: formatDate(end) }
}

export function shiftDateRange(
  start: string,
  end: string,
  direction: -1 | 1,
): { start: string; end: string } {
  const n = dayCount(start, end)
  const delta = direction * n
  return {
    start: formatDate(addDays(parseDate(start), delta)),
    end: formatDate(addDays(parseDate(end), delta)),
  }
}

export function gridTemplateColumns(dayCountValue: number): string {
  return `140px repeat(${Math.max(dayCountValue, 1)}, minmax(120px, 1fr))`
}

export function gridMinWidth(dayCountValue: number): number {
  return 140 + Math.max(dayCountValue, 1) * 120
}

export function monthOf(d: Date): string {
  return formatDate(d).slice(0, 7)
}

export type CalendarCell = {
  date: string
  dayNum: number
  outside: boolean
  isToday: boolean
}

/** 6x7 grid of calendar cells covering the month, weeks starting on Monday. */
export function calendarCells(month: string): CalendarCell[] {
  const first = parseDate(`${month}-01`)
  const start = mondayOf(first)
  const today = todayStr()
  return Array.from({ length: 42 }, (_, i) => {
    const d = addDays(start, i)
    const s = formatDate(d)
    return {
      date: s,
      dayNum: d.getDate(),
      outside: !s.startsWith(month),
      isToday: s === today,
    }
  })
}

/** Range covering the whole calendar grid of a month (for one query). */
export function calendarRange(month: string): { start: string; end: string } {
  const cells = calendarCells(month)
  return { start: cells[0].date, end: cells[cells.length - 1].date }
}

export function weekdayLabel(dateStr: string, locale: string): string {
  const zh = ['日', '一', '二', '三', '四', '五', '六']
  const en = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
  const idx = parseDate(dateStr).getDay()
  return locale.startsWith('en') ? en[idx] : `周${zh[idx]}`
}

export function monthDayLabel(dateStr: string): string {
  const d = parseDate(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

export type DaySummary = {
  headcount: number
  slots: number
  leaveHeadcount: number
  byLeave: { shift: Shift; count: number }[]
  /** counts per enabled shift; target/min/max from the rule set when enabled */
  byShift: {
    shift: Shift
    count: number
    target: number | null
    min: number | null
    max: number | null
  }[]
  /** enabled shifts with zero people that day */
  emptyShifts: number
  /** Total missing vs min / extra vs max; null when targets are off or unset. */
  gap: number | null
  overflow: number | null
}

/** Rule-set targets index Monday=0..Sunday=6. */
export function targetWeekdayIndex(dateStr: string): number {
  return (parseDate(dateStr).getDay() + 6) % 7
}

export function summarizeDay(
  dayAssignments: Assignment[],
  enabledShifts: Shift[],
  targets?: Record<string, TargetBand> | null,
  date?: string,
): DaySummary {
  const workShifts = enabledShifts.filter(
    (shift) => shift.is_enabled && (shift.shift_type ?? 'work') === 'work',
  )
  const leaveShifts = enabledShifts.filter((shift) => shift.shift_type === 'leave')
  const workAssignments = dayAssignments.filter((a) => (a.shift.shift_type ?? 'work') === 'work')
  const leaveAssignments = dayAssignments.filter((a) => a.shift.shift_type === 'leave')
  const people = new Set(workAssignments.map((a) => a.employee.id))
  const leavePeople = new Set(leaveAssignments.map((a) => a.employee.id))
  const countByShift = new Map<number, number>()
  for (const a of dayAssignments) {
    countByShift.set(a.shift.id, (countByShift.get(a.shift.id) ?? 0) + 1)
  }
  const weekday = date ? targetWeekdayIndex(date) : null
  const byShift = workShifts.map((shift) => {
    const count = countByShift.get(shift.id) ?? 0
    const band = targets && weekday != null ? targets[String(shift.id)] : null
    const target = band ? (band.target[weekday!] ?? null) : null
    const min = band ? (band.min[weekday!] ?? null) : null
    const max = band ? (band.max[weekday!] ?? null) : null
    return { shift, count, target, min, max }
  })
  const tracked = byShift.filter(
    (x) =>
      (x.min != null && x.min > 0) ||
      (x.target != null && x.target > 0) ||
      (x.max != null && x.max > 0),
  )
  return {
    headcount: people.size,
    slots: workAssignments.length,
    leaveHeadcount: leavePeople.size,
    byLeave: leaveShifts
      .map((shift) => ({ shift, count: countByShift.get(shift.id) ?? 0 }))
      .filter((item) => item.count > 0),
    byShift,
    emptyShifts: byShift.filter((x) => x.count === 0).length,
    gap:
      tracked.length > 0
        ? tracked.reduce((sum, x) => sum + Math.max(0, (x.min ?? 0) - x.count), 0)
        : null,
    overflow:
      tracked.length > 0
        ? tracked.reduce((sum, x) => {
            const max = x.max ?? 0
            return max > 0 ? sum + Math.max(0, x.count - max) : sum
          }, 0)
        : null,
  }
}

/** Group assignments by (shiftId, date) cell. */
export function assignmentsByCell(
  assignments: Assignment[],
): Map<string, Assignment[]> {
  const map = new Map<string, Assignment[]>()
  for (const a of assignments) {
    const key = `${a.shift.id}:${a.date}`
    const list = map.get(key)
    if (list) list.push(a)
    else map.set(key, [a])
  }
  return map
}

/** Group assignments by (employeeId, date) cell. */
export function assignmentsByAgentCell(
  assignments: Assignment[],
): Map<string, Assignment[]> {
  const map = new Map<string, Assignment[]>()
  for (const a of assignments) {
    const key = `${a.employee.id}:${a.date}`
    const list = map.get(key)
    if (list) list.push(a)
    else map.set(key, [a])
  }
  return map
}

/** Per-employee shift counts over the current board range (enabled-shift order, zeros omitted). */
export function agentPeriodShiftCounts(
  assignments: Assignment[],
  enabledShifts: Shift[],
): Map<number, { shift: Shift; count: number }[]> {
  const raw = new Map<number, Map<number, number>>()
  for (const a of assignments) {
    let byShift = raw.get(a.employee.id)
    if (!byShift) {
      byShift = new Map()
      raw.set(a.employee.id, byShift)
    }
    byShift.set(a.shift.id, (byShift.get(a.shift.id) ?? 0) + 1)
  }
  const result = new Map<number, { shift: Shift; count: number }[]>()
  const workShifts = enabledShifts.filter((shift) => (shift.shift_type ?? 'work') === 'work')
  for (const [employeeId, byShift] of raw) {
    result.set(
      employeeId,
      workShifts
        .map((shift) => ({ shift, count: byShift.get(shift.id) ?? 0 }))
        .filter((x) => x.count > 0),
    )
  }
  return result
}
