export type ConstraintLevel = 'hard' | 'soft'

export type ConstraintConfig = {
  enabled: boolean
  level: ConstraintLevel
  value?: number | null
}

export type RotationTemplateDay =
  | { kind: 'shift'; shift_id: number }
  | { kind: 'off' }

export type RotationTemplate = {
  id: string
  name: string
  is_default: boolean
  days: RotationTemplateDay[]
}

/** Per-shift Mon..Sun headcount bands. */
export type TargetBand = {
  min: number[]
  target: number[]
  max: number[]
}

export type RuleSet = {
  id: number
  name: string
  description: string | null
  is_default: boolean
  default_group_ids: number[]
  /** When false, generation uses rotation template only. */
  targets_enabled: boolean
  /** shift id (string) -> min/target/max week arrays */
  targets: Record<string, TargetBand>
  constraints: Record<string, ConstraintConfig>
  rotation_templates: RotationTemplate[]
  created_at: string | null
  updated_at: string | null
}

export type RuleSetListResponse = {
  items: RuleSet[]
}

export type RuleSetPayload = {
  name: string
  description?: string | null
  is_default?: boolean
  default_group_ids: number[]
  targets_enabled: boolean
  targets: Record<string, TargetBand>
  constraints: Record<string, ConstraintConfig>
  rotation_templates: RotationTemplate[]
}

const ZERO_WEEK = [0, 0, 0, 0, 0, 0, 0]

function asWeek(values: unknown): number[] | null {
  if (!Array.isArray(values) || values.length !== 7) return null
  const out: number[] = []
  for (const n of values) {
    if (typeof n !== 'number' || !Number.isFinite(n)) return null
    out.push(Math.max(0, Math.min(999, Math.round(n))))
  }
  return out
}

/** Normalize legacy [7 ints] or {min,target,max} into a TargetBand. */
export function normalizeTargetBand(raw: unknown): TargetBand {
  if (Array.isArray(raw)) {
    const days = asWeek(raw) ?? [...ZERO_WEEK]
    return { min: [...days], target: [...days], max: [...days] }
  }
  if (raw && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>
    const min = asWeek(obj.min) ?? [...ZERO_WEEK]
    const target = asWeek(obj.target) ?? [...ZERO_WEEK]
    const max = asWeek(obj.max) ?? [...ZERO_WEEK]
    return { min, target, max }
  }
  return { min: [...ZERO_WEEK], target: [...ZERO_WEEK], max: [...ZERO_WEEK] }
}

export function normalizeTargets(
  raw: Record<string, unknown> | null | undefined,
): Record<string, TargetBand> {
  if (!raw) return {}
  const out: Record<string, TargetBand> = {}
  for (const [key, value] of Object.entries(raw)) {
    out[key] = normalizeTargetBand(value)
  }
  return out
}

export function emptyTargetBand(): TargetBand {
  return { min: [...ZERO_WEEK], target: [...ZERO_WEEK], max: [...ZERO_WEEK] }
}

/** Clamp a band so 0 ≤ min ≤ target ≤ max ≤ 999 after editing one field. */
export function clampTargetBand(band: TargetBand, dayIndex: number, field: keyof TargetBand, value: number): TargetBand {
  const next: TargetBand = {
    min: [...band.min],
    target: [...band.target],
    max: [...band.max],
  }
  const v = Math.max(0, Math.min(999, value))
  next[field][dayIndex] = v
  if (next.min[dayIndex] > next.target[dayIndex]) {
    if (field === 'min') next.target[dayIndex] = next.min[dayIndex]
    else next.min[dayIndex] = next.target[dayIndex]
  }
  if (next.target[dayIndex] > next.max[dayIndex]) {
    if (field === 'max') next.target[dayIndex] = next.max[dayIndex]
    else next.max[dayIndex] = next.target[dayIndex]
  }
  if (next.min[dayIndex] > next.max[dayIndex]) {
    if (field === 'min') next.max[dayIndex] = next.min[dayIndex]
    else next.min[dayIndex] = next.max[dayIndex]
  }
  return next
}

export type ConstraintDef = {
  key: string
  /** numeric param range; null = toggle-only constraint (fixed soft) */
  param: { min: number; max: number; defaultValue: number } | null
  defaultLevel: ConstraintLevel
  /** whether the level can be toggled between hard/soft */
  levelEditable: boolean
}

/** The 7 fixed work-hour constraints, in display order. */
export const CONSTRAINT_DEFS: ConstraintDef[] = [
  { key: 'max_consecutive_days', param: { min: 1, max: 31, defaultValue: 6 }, defaultLevel: 'hard', levelEditable: true },
  { key: 'min_rest_hours', param: { min: 0, max: 48, defaultValue: 8 }, defaultLevel: 'hard', levelEditable: true },
  { key: 'max_weekly_work_days', param: { min: 1, max: 7, defaultValue: 6 }, defaultLevel: 'hard', levelEditable: true },
  { key: 'max_daily_shifts', param: { min: 1, max: 6, defaultValue: 2 }, defaultLevel: 'soft', levelEditable: true },
  { key: 'coverage_gap', param: null, defaultLevel: 'soft', levelEditable: false },
  { key: 'coverage_overflow', param: null, defaultLevel: 'soft', levelEditable: false },
  { key: 'fairness_deviation', param: { min: 0, max: 14, defaultValue: 2 }, defaultLevel: 'soft', levelEditable: true },
]

export function defaultConstraints(): Record<string, ConstraintConfig> {
  const result: Record<string, ConstraintConfig> = {}
  for (const def of CONSTRAINT_DEFS) {
    result[def.key] = {
      enabled: false,
      level: def.defaultLevel,
      value: def.param?.defaultValue ?? null,
    }
  }
  return result
}

// ------------------------------------------------------------------
// Violations & rule-based generation
// ------------------------------------------------------------------

export type RuleViolation = {
  level: ConstraintLevel
  constraint: string
  /** YYYY-MM-DD */
  date: string
  employee_id: number | null
  employee_name: string | null
  shift_id: number | null
  shift_name: string | null
  detail: Record<string, number>
}

export type ViolationListResponse = {
  items: RuleViolation[]
  hard_count: number
  soft_count: number
}

export type GeneratePayload = {
  rule_set_id: number
  /** YYYY-MM-DD */
  start_date: string
  /** YYYY-MM-DD */
  end_date: string
  mode: 'fill' | 'clear'
  use_template: boolean
  on_hard_conflict: 'skip' | 'abort'
  group_ids: number[]
}

export type GenerateSampleLine = {
  date: string
  shift_id: number
  shift_name: string
  added: string[]
  gap: number
}

export type GeneratePreviewResponse = {
  to_create: number
  to_delete: number
  skipped_cells: number
  leave_skipped: number
  target_met: number
  target_total: number
  hard_count: number
  soft_count: number
  hard_violations: RuleViolation[]
  soft_violations: RuleViolation[]
  sample: GenerateSampleLine[]
}

export type GenerateApplyResponse = {
  created: number
  deleted: number
}
