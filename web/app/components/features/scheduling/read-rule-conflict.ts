import { HTTPError } from 'ky'
import type { RuleViolation } from '@/models/scheduling-rule'

export type RuleConflict = {
  code: 'RULE_HARD_VIOLATION' | 'RULE_SOFT_VIOLATION'
  violations: RuleViolation[]
}

export type LeaveWorkConflict = {
  code: 'LEAVE_WORK_CONFLICT'
  affectedEmployeeDates: number
}

export type ScheduleWriteConflict = RuleConflict | LeaveWorkConflict

/** Extract a scheduling rule conflict (409) from a ky HTTPError; else null. */
export async function readRuleConflict(error: unknown): Promise<ScheduleWriteConflict | null> {
  if (!(error instanceof HTTPError)) return null
  if (error.response.status !== 409) return null
  try {
    const body = (await error.response.json()) as {
      code?: string
      details?: { violations?: RuleViolation[]; affected_employee_dates?: number }
    }
    if (body.code === 'RULE_HARD_VIOLATION' || body.code === 'RULE_SOFT_VIOLATION') {
      return { code: body.code, violations: body.details?.violations ?? [] }
    }
    if (body.code === 'LEAVE_WORK_CONFLICT') {
      return {
        code: body.code,
        affectedEmployeeDates: body.details?.affected_employee_dates ?? 0,
      }
    }
  } catch {
    // ignore JSON parse errors
  }
  return null
}
