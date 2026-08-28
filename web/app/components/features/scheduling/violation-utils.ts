import type { Assignment } from '@/models/scheduling'
import type { RuleViolation } from '@/models/scheduling-rule'
import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'

/** Human-readable one-line description of a violation (drawer, badges, dialogs). */
export function violationText(v: RuleViolation, locale: Locale): string {
  const params = { ...v.detail }
  return t(`scheduling.violation.${v.constraint}`, locale, params)
}

/** Display name of the violation subject: employee name or shift name. */
export function violationSubject(v: RuleViolation): string {
  return v.employee_name ?? v.shift_name ?? ''
}

/**
 * Map violations onto shift-day grid cells ("shiftId:date").
 * Coverage violations attach to their cell directly; employee-bound
 * violations attach to every shift cell the employee appears in that day.
 */
export function shiftCellViolations(
  violations: RuleViolation[],
  assignments: Assignment[],
): Map<string, RuleViolation[]> {
  const map = new Map<string, RuleViolation[]>()
  const push = (key: string, v: RuleViolation) => {
    const list = map.get(key)
    if (list) list.push(v)
    else map.set(key, [v])
  }
  const employeeCells = new Map<string, string[]>()
  for (const a of assignments) {
    const key = `${a.employee.id}:${a.date}`
    const list = employeeCells.get(key)
    const cellKey = `${a.shift.id}:${a.date}`
    if (list) list.push(cellKey)
    else employeeCells.set(key, [cellKey])
  }
  for (const v of violations) {
    if (v.shift_id != null) {
      push(`${v.shift_id}:${v.date}`, v)
      continue
    }
    if (v.employee_id != null) {
      for (const cellKey of employeeCells.get(`${v.employee_id}:${v.date}`) ?? []) {
        push(cellKey, v)
      }
    }
  }
  return map
}

/** Map employee-bound violations onto agent-day grid cells ("employeeId:date"). */
export function agentCellViolations(
  violations: RuleViolation[],
): Map<string, RuleViolation[]> {
  const map = new Map<string, RuleViolation[]>()
  for (const v of violations) {
    if (v.employee_id == null) continue
    const key = `${v.employee_id}:${v.date}`
    const list = map.get(key)
    if (list) list.push(v)
    else map.set(key, [v])
  }
  return map
}

/** Worst level of a cell's violations drives the badge color. */
export function cellLevel(list: RuleViolation[] | undefined): 'hard' | 'soft' | null {
  if (!list || list.length === 0) return null
  return list.some((v) => v.level === 'hard') ? 'hard' : 'soft'
}
