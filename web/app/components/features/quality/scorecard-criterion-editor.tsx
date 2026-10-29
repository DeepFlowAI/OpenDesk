'use client'

import { IconPlus, IconTrash } from '@tabler/icons-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import type { QualityScorecardCriterionInput, QualityScorecardOptionInput } from '@/models/quality-scorecard'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'

type Props = {
  criterion: QualityScorecardCriterionInput
  disabled: boolean
  onChange: (criterion: QualityScorecardCriterionInput) => void
  onRemove: () => void
}

const severityOptions = ['normal', 'notice', 'issue', 'serious', 'fatal'] as const

function blankOption(maxPoints: number): QualityScorecardOptionInput {
  return { name: '', description: '', points: maxPoints, severity: 'normal' }
}

export function ScorecardCriterionEditor({ criterion, disabled, onChange, onRemove }: Props) {
  const { locale } = useLocaleStore()
  const updateOption = (index: number, patch: Partial<QualityScorecardOptionInput>) => {
    const options = criterion.options.map((option, optionIndex) => (
      optionIndex === index ? { ...option, ...patch } : option
    ))
    onChange({ ...criterion, options })
  }

  return (
    <section className="space-y-4 rounded-lg border border-border bg-card p-4">
      <div className="flex items-start gap-3">
        <div className="grid flex-1 gap-3 md:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span>{t('ws.quality.scorecard.criterionName', locale)}</span>
            <Input disabled={disabled} value={criterion.name} onChange={(event) => onChange({ ...criterion, name: event.target.value })} />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t('ws.quality.scorecard.maxPoints', locale)}</span>
            <Input disabled={disabled} type="number" min={0} max={100} step="0.01" value={criterion.max_points} onChange={(event) => onChange({ ...criterion, max_points: Number(event.target.value) })} />
          </label>
          <label className="space-y-1 text-sm md:col-span-2">
            <span>{t('ws.quality.scorecard.rubric', locale)}</span>
            <Textarea disabled={disabled} value={criterion.rubric} onChange={(event) => onChange({ ...criterion, rubric: event.target.value })} />
          </label>
          <label className="space-y-1 text-sm">
            <span>{t('ws.quality.scorecard.evidencePolicy', locale)}</span>
            <select disabled={disabled} value={criterion.evidence_policy} onChange={(event) => onChange({ ...criterion, evidence_policy: event.target.value as QualityScorecardCriterionInput['evidence_policy'] })} className="h-8 w-full rounded-lg border border-input bg-background px-2.5">
              <option value="none">{t('ws.quality.scorecard.evidence.none', locale)}</option><option value="issue_only">{t('ws.quality.scorecard.evidence.issueOnly', locale)}</option><option value="always">{t('ws.quality.scorecard.evidence.always', locale)}</option>
            </select>
          </label>
          <label className="flex items-center gap-2 self-end pb-1 text-sm">
            <input disabled={disabled} type="checkbox" checked={criterion.is_required} onChange={(event) => onChange({ ...criterion, is_required: event.target.checked })} /> {t('ws.quality.scorecard.required', locale)}
          </label>
        </div>
        {!disabled && <Button variant="ghost" size="icon" aria-label={t('ws.quality.scorecard.removeCriterion', locale)} onClick={onRemove}><IconTrash /></Button>}
      </div>

      <div className="space-y-2">
        <div className="grid grid-cols-[1fr_1.5fr_100px_130px_32px] gap-2 text-xs text-muted-foreground">
          <span>{t('ws.quality.scorecard.optionName', locale)}</span><span>{t('ws.quality.scorecard.optionDescription', locale)}</span><span>{t('ws.quality.review.score', locale)}</span><span>{t('ws.quality.scorecard.severity', locale)}</span><span />
        </div>
        {criterion.options.map((option, index) => (
          <div key={`${index}-${option.name}`} className="grid grid-cols-[1fr_1.5fr_100px_130px_32px] gap-2">
            <Input disabled={disabled} value={option.name} onChange={(event) => updateOption(index, { name: event.target.value })} />
            <Input disabled={disabled} value={option.description} onChange={(event) => updateOption(index, { description: event.target.value })} />
            <Input disabled={disabled} type="number" min={0} max={criterion.max_points} step="0.01" value={option.points} onChange={(event) => updateOption(index, { points: Number(event.target.value) })} />
            <select disabled={disabled} value={option.severity} onChange={(event) => updateOption(index, { severity: event.target.value as QualityScorecardOptionInput['severity'] })} className="h-8 rounded-lg border border-input bg-background px-2">
              {severityOptions.map((severity) => <option key={severity} value={severity}>{t(`ws.quality.severity.${severity}`, locale)}</option>)}
            </select>
            {!disabled && <Button variant="ghost" size="icon" disabled={criterion.options.length <= 2} onClick={() => onChange({ ...criterion, options: criterion.options.filter((_, optionIndex) => optionIndex !== index) })}><IconTrash /></Button>}
          </div>
        ))}
        {!disabled && criterion.options.length < 5 && <Button variant="outline" onClick={() => onChange({ ...criterion, options: [...criterion.options, blankOption(criterion.max_points)] })}><IconPlus />{t('ws.quality.scorecard.addOption', locale)}</Button>}
      </div>
    </section>
  )
}
