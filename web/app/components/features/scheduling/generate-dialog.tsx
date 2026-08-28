'use client'

import { useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import { IconAlertTriangle } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Shift } from '@/models/scheduling'
import type { GeneratePayload, GeneratePreviewResponse } from '@/models/scheduling-rule'
import { useGenerateApply, useGeneratePreview } from '@/service/use-scheduling'
import { useRuleSets } from '@/service/use-scheduling-rules'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { Button } from '@/components/ui/button'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { Switch } from '@/components/ui/switch'
import { constraintSummary, targetSummary } from './rules/rule-summary'
import { violationText, violationSubject } from './violation-utils'
import { dayCount } from './board-utils'

const MAX_GENERATE_DAYS = 31

export type GenerateDialogProps = {
  open: boolean
  groupIds: number[]
  startDate: string
  endDate: string
  shifts: Shift[]
  onClose: () => void
  onApplied: () => void
}

export function GenerateDialog({
  open,
  groupIds,
  startDate,
  endDate,
  shifts,
  onClose,
  onApplied,
}: GenerateDialogProps) {
  const { locale } = useLocaleStore()
  const ruleSetsQuery = useRuleSets(open)
  const ruleSets = useMemo(() => ruleSetsQuery.data?.items ?? [], [ruleSetsQuery.data])

  const [ruleSetId, setRuleSetId] = useState<number | null>(null)
  const [mode, setMode] = useState<'fill' | 'clear'>('fill')
  const [useTemplate, setUseTemplate] = useState(true)
  const [onHardConflict, setOnHardConflict] = useState<'skip' | 'abort'>('skip')
  const [preview, setPreview] = useState<GeneratePreviewResponse | null>(null)
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false)

  const previewMutation = useGeneratePreview()
  const applyMutation = useGenerateApply()

  useEffect(() => {
    if (!open) return
    setMode('fill')
    setUseTemplate(true)
    setOnHardConflict('skip')
    setPreview(null)
    setClearConfirmOpen(false)
    setRuleSetId(null)
  }, [open])

  // Preselect the tenant default once rule sets load.
  useEffect(() => {
    if (!open || ruleSetId != null || ruleSets.length === 0) return
    setRuleSetId((ruleSets.find((rs) => rs.is_default) ?? ruleSets[0]).id)
  }, [open, ruleSetId, ruleSets])

  const selectedRuleSet = ruleSets.find((rs) => rs.id === ruleSetId) ?? null
  const hasTemplates = (selectedRuleSet?.rotation_templates.length ?? 0) > 0
  const rangeDays = dayCount(startDate, endDate)
  const rangeOverMax = rangeDays > MAX_GENERATE_DAYS

  const buildPayload = (): GeneratePayload | null => {
    if (ruleSetId == null) return null
    return {
      rule_set_id: ruleSetId,
      start_date: startDate,
      end_date: endDate,
      mode,
      use_template: useTemplate && hasTemplates,
      on_hard_conflict: onHardConflict,
      group_ids: groupIds,
    }
  }

  const runPreview = async () => {
    const payload = buildPayload()
    if (!payload) return
    try {
      setPreview(await previewMutation.mutateAsync(payload))
    } catch {
      toast.error(t('scheduling.generate.toast.previewFailed', locale))
    }
  }

  const runApply = async () => {
    const payload = buildPayload()
    if (!payload) return
    try {
      await applyMutation.mutateAsync(payload)
      toast.success(t('scheduling.generate.toast.applied', locale))
      setClearConfirmOpen(false)
      onApplied()
      onClose()
    } catch {
      toast.error(t('scheduling.board.toast.opFailed', locale))
    }
  }

  const onConfirmWrite = () => {
    if (mode === 'clear') setClearConfirmOpen(true)
    else void runApply()
  }

  const submitting = previewMutation.isPending || applyMutation.isPending

  return (
    <>
      <Dialog open={open} onOpenChange={(next) => { if (!next) onClose() }}>
        <DialogContent
          overlayClassName="supports-backdrop-filter:backdrop-blur-none"
          className="flex max-h-[85vh] flex-col gap-0 p-0 sm:max-w-[640px]"
        >
          <DialogHeader className="border-b px-5 py-4">
            <DialogTitle>{t('scheduling.generate.title', locale)}</DialogTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {startDate} ~ {endDate}
            </p>
          </DialogHeader>

          <div className="min-h-0 flex-1 space-y-4 overflow-auto px-5 py-4">
            {ruleSetsQuery.isLoading ? (
              <p className="py-6 text-center text-xs text-muted-foreground">
                {t('scheduling.rules.loading', locale)}
              </p>
            ) : ruleSets.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center">
                <p className="text-sm text-muted-foreground">
                  {t('scheduling.generate.emptyRuleSets', locale)}
                </p>
                <Link href="/scheduling/rules/new" className="mt-3 inline-block">
                  <Button size="sm">{t('scheduling.rules.new', locale)}</Button>
                </Link>
              </div>
            ) : (
              <>
                <div>
                  <div className="mb-2 text-xs font-medium text-muted-foreground">
                    {t('scheduling.generate.ruleSet', locale)}
                  </div>
                  <div className="space-y-2">
                    {ruleSets.map((rs) => (
                      <button
                        key={rs.id}
                        type="button"
                        onClick={() => {
                          setRuleSetId(rs.id)
                          setPreview(null)
                        }}
                        className={`flex w-full items-start gap-3 rounded-lg border px-3 py-2.5 text-left ${
                          ruleSetId === rs.id
                            ? 'border-primary bg-primary/5'
                            : 'border-border bg-background'
                        }`}
                      >
                        <span
                          className={`mt-1 h-3.5 w-3.5 shrink-0 rounded-full border ${
                            ruleSetId === rs.id
                              ? 'border-primary bg-primary ring-2 ring-inset ring-white'
                              : 'border-border'
                          }`}
                        />
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-2 text-sm font-medium">
                            <span className="truncate">{rs.name}</span>
                            {rs.is_default && (
                              <span className="rounded bg-primary/10 px-1.5 py-px text-[10px] text-primary">
                                {t('scheduling.rules.default', locale)}
                              </span>
                            )}
                          </span>
                          <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                            {targetSummary(rs, shifts, locale) || '—'} ·{' '}
                            {constraintSummary(rs.constraints, locale) || '—'}
                          </span>
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="mb-1.5 text-xs font-medium text-muted-foreground">
                      {t('scheduling.generate.mode', locale)}
                    </div>
                    <RadioGroup
                      value={mode}
                      onValueChange={(v) => {
                        setMode(v as 'fill' | 'clear')
                        setPreview(null)
                      }}
                      className="flex h-9 items-center gap-4 rounded-md border border-border px-3"
                    >
                      {(['fill', 'clear'] as const).map((value) => (
                        <label key={value} className="inline-flex cursor-pointer items-center gap-1.5 text-xs">
                          <RadioGroupItem value={value} />
                          {t(`scheduling.generate.mode.${value}`, locale)}
                        </label>
                      ))}
                    </RadioGroup>
                  </div>
                  <div>
                    <div className="mb-1.5 text-xs font-medium text-muted-foreground">
                      {t('scheduling.generate.onHardConflict', locale)}
                    </div>
                    <RadioGroup
                      value={onHardConflict}
                      onValueChange={(v) => setOnHardConflict(v as 'skip' | 'abort')}
                      className="flex h-9 items-center gap-4 rounded-md border border-border px-3"
                    >
                      {(['skip', 'abort'] as const).map((value) => (
                        <label key={value} className="inline-flex cursor-pointer items-center gap-1.5 text-xs">
                          <RadioGroupItem value={value} />
                          {t(`scheduling.generate.conflict.${value}`, locale)}
                        </label>
                      ))}
                    </RadioGroup>
                  </div>
                </div>

                {mode === 'clear' && (
                  <div className="flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50/70 px-3 py-2.5 text-xs text-amber-900">
                    <IconAlertTriangle size={14} className="mt-0.5 shrink-0" />
                    {t('scheduling.generate.mode.clearWarn', locale)}
                  </div>
                )}

                {hasTemplates && (
                  <label className="flex items-center justify-between rounded-md border border-border px-3 py-2.5 text-xs">
                    <span>{t('scheduling.generate.useTemplate', locale)}</span>
                    <Switch
                      checked={useTemplate}
                      onCheckedChange={(checked) => {
                        setUseTemplate(checked)
                        setPreview(null)
                      }}
                    />
                  </label>
                )}

                {rangeOverMax && (
                  <p className="text-xs text-destructive">
                    {t('scheduling.generate.rangeOverMax', locale, { max: MAX_GENERATE_DAYS })}
                  </p>
                )}

                {preview && (
                  <>
                    <div className="grid grid-cols-5 gap-3">
                      {[
                        {
                          label: t('scheduling.generate.stats.create', locale),
                          value: t('scheduling.generate.stats.rows', locale, { count: preview.to_create }),
                        },
                        {
                          label: t('scheduling.generate.stats.delete', locale),
                          value: t('scheduling.generate.stats.rows', locale, { count: preview.to_delete }),
                        },
                        {
                          label: t('scheduling.generate.stats.skip', locale),
                          value: t('scheduling.generate.stats.cells', locale, { count: preview.skipped_cells }),
                        },
                        {
                          label: t('scheduling.generate.stats.leaveSkipped', locale),
                          value: t('scheduling.generate.stats.days', locale, { count: preview.leave_skipped }),
                        },
                        {
                          label: t('scheduling.generate.stats.target', locale),
                          value:
                            selectedRuleSet?.targets_enabled === false || preview.target_total === 0
                              ? '—'
                              : `${preview.target_met} / ${preview.target_total}`,
                        },
                      ].map((x) => (
                        <div
                          key={x.label}
                          className="rounded-lg border border-border bg-muted/30 px-3 py-2.5"
                        >
                          <div className="text-[11px] text-muted-foreground">{x.label}</div>
                          <div className="mt-1 text-sm font-semibold tabular-nums">{x.value}</div>
                        </div>
                      ))}
                    </div>

                    {preview.soft_count > 0 && (
                      <div className="rounded-lg border border-amber-200 bg-amber-50/60 px-3 py-2.5 text-xs">
                        <div className="font-medium text-amber-900">
                          {t('scheduling.generate.stats.soft', locale, { count: preview.soft_count })}
                        </div>
                        <ul className="mt-1 space-y-0.5 text-amber-800">
                          {preview.soft_violations.map((v, i) => (
                            <li key={i}>
                              {violationSubject(v)} · {v.date} · {violationText(v, locale)}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {preview.sample.length > 0 && (
                      <div className="rounded-lg border border-border">
                        <div className="border-b border-border bg-muted/40 px-3 py-2 text-xs font-medium text-muted-foreground">
                          {t('scheduling.generate.sampleTitle', locale)}
                        </div>
                        <div className="max-h-[160px] overflow-auto">
                          {preview.sample.map((line) => (
                            <div
                              key={`${line.shift_id}:${line.date}`}
                              className="border-b border-border px-3 py-2 text-xs last:border-b-0"
                            >
                              {line.date} · {line.shift_name} ← {line.added.join('、')}
                              {line.gap > 0 &&
                                `（${t('scheduling.generate.sampleGap', locale, { count: line.gap })}）`}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    <p className="text-[11px] text-muted-foreground">
                      {t('scheduling.generate.note', locale)}
                    </p>
                  </>
                )}
              </>
            )}
          </div>

          <DialogFooter className="px-5 py-4">
            <Button variant="outline" onClick={onClose} disabled={submitting}>
              {t('scheduling.form.cancel', locale)}
            </Button>
            <Button
              variant="outline"
              onClick={runPreview}
              disabled={submitting || ruleSetId == null || rangeOverMax}
            >
              {previewMutation.isPending
                ? t('scheduling.generate.previewing', locale)
                : t('scheduling.generate.preview', locale)}
            </Button>
            <Button
              onClick={onConfirmWrite}
              disabled={submitting || preview == null}
            >
              {applyMutation.isPending
                ? t('scheduling.generate.applying', locale)
                : t('scheduling.generate.confirmWrite', locale)}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={clearConfirmOpen}
        title={t('scheduling.generate.clearConfirm.title', locale)}
        message={t('scheduling.generate.clearConfirm.message', locale)}
        confirmLabel={t('scheduling.generate.clearConfirm.confirm', locale)}
        cancelLabel={t('scheduling.form.cancel', locale)}
        variant="destructive"
        loading={applyMutation.isPending}
        onCancel={() => setClearConfirmOpen(false)}
        onConfirm={runApply}
      />
    </>
  )
}
