import type { ConstraintConfig, RuleSet, TargetBand } from '@/models/scheduling-rule'
import { CONSTRAINT_DEFS } from '@/models/scheduling-rule'
import type { Shift } from '@/models/scheduling'
import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'

/** Short constraint summary for the rule set list, e.g. "连上≤6 · 休息≥8h". */
export function constraintSummary(
  constraints: Record<string, ConstraintConfig>,
  locale: Locale,
): string {
  const parts: string[] = []
  for (const def of CONSTRAINT_DEFS) {
    const cfg = constraints[def.key]
    if (!cfg?.enabled) continue
    if (def.param) {
      parts.push(t(`scheduling.rules.constraint.short.${def.key}`, locale, { v: cfg.value ?? def.param.defaultValue }))
    } else {
      parts.push(t(`scheduling.rules.constraint.short.${def.key}`, locale))
    }
  }
  return parts.join(' · ')
}

function avg(values: number[]): number {
  if (values.length === 0) return 0
  return Math.round(values.reduce((a, b) => a + b, 0) / values.length)
}

function bandActive(band: TargetBand): boolean {
  return (
    band.min.some((n) => n > 0) ||
    band.target.some((n) => n > 0) ||
    band.max.some((n) => n > 0)
  )
}

/** Coverage target summary, e.g. "早班 目标4（1–6）". */
export function targetSummary(
  ruleSet: Pick<RuleSet, 'targets' | 'targets_enabled'>,
  shifts: Shift[],
  locale: Locale,
): string {
  if (ruleSet.targets_enabled === false) {
    return t('scheduling.rules.targetSummary.disabled', locale)
  }
  const parts: string[] = []
  for (const shift of shifts) {
    const band = ruleSet.targets[String(shift.id)]
    if (!band || !bandActive(band)) continue
    const weekday = avg(band.target.slice(0, 5))
    const weekend = avg(band.target.slice(5, 7))
    const targetLabel = weekday === weekend ? String(weekday) : `${weekday}/${weekend}`
    const minAvg = avg(band.min)
    const maxAvg = avg(band.max)
    if (minAvg === maxAvg && weekday === weekend) {
      parts.push(t('scheduling.rules.targetSummary.same', locale, { name: shift.name, count: weekday }))
    } else {
      parts.push(
        t('scheduling.rules.targetSummary.banded', locale, {
          name: shift.name,
          target: targetLabel,
          min: minAvg,
          max: maxAvg,
        }),
      )
    }
  }
  return parts.join(' · ')
}
