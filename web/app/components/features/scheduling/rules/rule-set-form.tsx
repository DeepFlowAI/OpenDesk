'use client'

import { useEffect, useMemo, useState } from 'react'
import { useRouter } from 'next/navigation'
import { IconPlus, IconStar, IconTrash } from '@tabler/icons-react'
import { toast } from 'sonner'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import {
  CONSTRAINT_DEFS,
  clampTargetBand,
  defaultConstraints,
  emptyTargetBand,
  normalizeTargets,
  type ConstraintConfig,
  type RotationTemplate,
  type RuleSet,
  type RuleSetPayload,
  type TargetBand,
} from '@/models/scheduling-rule'
import { useShifts } from '@/service/use-scheduling'
import {
  useCreateRuleSet,
  useSetDefaultRuleSet,
  useUpdateRuleSet,
} from '@/service/use-scheduling-rules'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { PoolPicker } from '@/app/components/features/scheduling/pool-picker'
import { RotationTemplateDialog } from '@/app/components/features/scheduling/rules/rotation-template-dialog'

const WEEKDAY_KEYS = ['1', '2', '3', '4', '5', '6', '0'] as const

type DraftState = {
  name: string
  description: string
  defaultGroupIds: number[]
  isDefault: boolean
  targetsEnabled: boolean
  targets: Record<string, TargetBand>
  constraints: Record<string, ConstraintConfig>
  templates: RotationTemplate[]
}

function initDraft(ruleSet: RuleSet | undefined): DraftState {
  if (!ruleSet) {
    return {
      name: '',
      description: '',
      defaultGroupIds: [],
      isDefault: false,
      targetsEnabled: true,
      targets: {},
      constraints: defaultConstraints(),
      templates: [],
    }
  }
  const constraints = defaultConstraints()
  for (const def of CONSTRAINT_DEFS) {
    const cfg = ruleSet.constraints[def.key]
    if (cfg) constraints[def.key] = { ...constraints[def.key], ...cfg }
  }
  return {
    name: ruleSet.name,
    description: ruleSet.description ?? '',
    defaultGroupIds: ruleSet.default_group_ids,
    isDefault: ruleSet.is_default,
    targetsEnabled: ruleSet.targets_enabled !== false,
    targets: normalizeTargets(ruleSet.targets as unknown as Record<string, unknown>),
    constraints,
    templates: ruleSet.rotation_templates,
  }
}

export type RuleSetFormProps = {
  /** Existing rule set to edit; undefined = create new. */
  ruleSet?: RuleSet
}

export function RuleSetForm({ ruleSet }: RuleSetFormProps) {
  const { locale } = useLocaleStore()
  const router = useRouter()
  const { data: shiftsData } = useShifts()
  const createMutation = useCreateRuleSet()
  const updateMutation = useUpdateRuleSet()
  const setDefaultMutation = useSetDefaultRuleSet()

  const isEdit = Boolean(ruleSet)
  const enabledShifts = useMemo(
    () =>
      (shiftsData?.items ?? []).filter(
        (s) => s.is_enabled && (s.shift_type ?? 'work') === 'work',
      ),
    [shiftsData],
  )

  const [draft, setDraft] = useState<DraftState>(() => initDraft(ruleSet))
  const [snapshot, setSnapshot] = useState(() => JSON.stringify(initDraft(ruleSet)))
  const [nameError, setNameError] = useState('')
  const [leaveConfirm, setLeaveConfirm] = useState(false)
  const [templateDialog, setTemplateDialog] = useState<{
    open: boolean
    template: RotationTemplate | null
  }>({ open: false, template: null })

  const dirty = useMemo(() => JSON.stringify(draft) !== snapshot, [draft, snapshot])
  const saving = createMutation.isPending || updateMutation.isPending

  // Warn before browser unload when there are unsaved changes.
  useEffect(() => {
    if (!dirty) return
    const handler = (e: BeforeUnloadEvent) => e.preventDefault()
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirty])

  const patchDraft = (partial: Partial<DraftState>) =>
    setDraft((prev) => ({ ...prev, ...partial }))

  const setTargetField = (
    shiftId: number,
    dayIndex: number,
    field: keyof TargetBand,
    value: number,
  ) => {
    const key = String(shiftId)
    const band = draft.targets[key] ?? emptyTargetBand()
    patchDraft({
      targets: {
        ...draft.targets,
        [key]: clampTargetBand(band, dayIndex, field, value),
      },
    })
  }

  const setConstraint = (key: string, cfg: Partial<ConstraintConfig>) => {
    patchDraft({ constraints: { ...draft.constraints, [key]: { ...draft.constraints[key], ...cfg } } })
  }

  const saveTemplate = (template: RotationTemplate) => {
    setDraft((prev) => {
      let templates = prev.templates.filter((tpl) => tpl.id !== template.id)
      // Only one default template per rule set.
      const next = template.is_default
        ? templates.map((tpl) => ({ ...tpl, is_default: false }))
        : templates
      templates = [...next, template]
      return { ...prev, templates }
    })
    setTemplateDialog({ open: false, template: null })
  }

  const removeTemplate = (id: string) => {
    patchDraft({ templates: draft.templates.filter((tpl) => tpl.id !== id) })
  }

  const buildPayload = (): RuleSetPayload | null => {
    const name = draft.name.trim()
    if (!name) {
      setNameError(t('scheduling.rules.form.err.nameRequired', locale))
      return null
    }
    if (name.length > 40) {
      setNameError(t('scheduling.rules.form.err.nameTooLong', locale))
      return null
    }
    setNameError('')
    const validShiftIds = new Set(enabledShifts.map((shift) => shift.id))
    return {
      name,
      description: draft.description.trim() || null,
      is_default: draft.isDefault,
      default_group_ids: draft.defaultGroupIds,
      targets_enabled: draft.targetsEnabled,
      targets: Object.fromEntries(
        Object.entries(draft.targets).filter(([shiftId]) => validShiftIds.has(Number(shiftId))),
      ),
      constraints: draft.constraints,
      rotation_templates: draft.templates
        .map((template) => ({
          ...template,
          days: template.days.filter(
            (day) => day.kind === 'off' || validShiftIds.has(day.shift_id),
          ),
        }))
        .filter((template) => template.days.length >= 2),
    }
  }

  const handleSave = async () => {
    const payload = buildPayload()
    if (!payload) return
    try {
      if (isEdit && ruleSet) {
        const saved = await updateMutation.mutateAsync({ id: ruleSet.id, ...payload })
        setSnapshot(JSON.stringify(initDraft(saved)))
        toast.success(t('scheduling.rules.toast.saved', locale))
      } else {
        const saved = await createMutation.mutateAsync(payload)
        toast.success(t('scheduling.rules.toast.saved', locale))
        router.replace(`/scheduling/rules/${saved.id}`)
      }
    } catch {
      toast.error(t('scheduling.rules.toast.saveFailed', locale))
    }
  }

  const handleSetDefault = async () => {
    if (!ruleSet) return
    try {
      const saved = await setDefaultMutation.mutateAsync(ruleSet.id)
      setDraft((prev) => ({ ...prev, isDefault: saved.is_default }))
      setSnapshot(JSON.stringify({ ...draft, isDefault: saved.is_default }))
      toast.success(t('scheduling.rules.toast.setDefault', locale))
    } catch {
      toast.error(t('scheduling.rules.toast.opFailed', locale))
    }
  }

  const handleBack = () => {
    if (dirty) setLeaveConfirm(true)
    else router.push('/scheduling/rules')
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 items-center justify-between border-b border-border bg-white px-8 py-4">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            className="shrink-0 text-sm text-muted-foreground hover:text-foreground"
            onClick={handleBack}
          >
            ← {t('scheduling.rules.back', locale)}
          </button>
          <span className="text-border">|</span>
          <h1 className="truncate text-lg font-semibold">
            {isEdit ? draft.name || ruleSet?.name : t('scheduling.rules.newTitle', locale)}
          </h1>
          {draft.isDefault && (
            <span className="inline-flex shrink-0 items-center gap-0.5 rounded-md bg-primary/10 px-2 py-0.5 text-[11px] text-primary">
              <IconStar size={12} />
              {t('scheduling.rules.default', locale)}
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {isEdit && !draft.isDefault && (
            <Button
              variant="outline"
              onClick={handleSetDefault}
              disabled={setDefaultMutation.isPending}
            >
              {t('scheduling.rules.setDefault', locale)}
            </Button>
          )}
          <Button onClick={handleSave} disabled={saving}>
            {saving ? t('scheduling.form.submitting', locale) : t('scheduling.form.submit', locale)}
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 space-y-6 overflow-auto px-8 py-6">
        <section className="rounded-xl border border-border bg-white p-5">
          <h2 className="text-sm font-semibold">{t('scheduling.rules.section.basic', locale)}</h2>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <label className="block text-xs text-muted-foreground">
              {t('scheduling.rules.form.name', locale)}
              <Input
                className="mt-1"
                value={draft.name}
                maxLength={40}
                onChange={(e) => patchDraft({ name: e.target.value })}
                placeholder={t('scheduling.rules.form.namePlaceholder', locale)}
              />
              {nameError && <span className="mt-1 block text-xs text-destructive">{nameError}</span>}
            </label>
            <label className="block text-xs text-muted-foreground">
              {t('scheduling.rules.form.defaultGroups', locale)}
              <div className="mt-1">
                <PoolPicker
                  groupIds={draft.defaultGroupIds}
                  onGroupIdsChange={(ids) => patchDraft({ defaultGroupIds: ids })}
                />
              </div>
            </label>
            <label className="col-span-2 block text-xs text-muted-foreground">
              {t('scheduling.rules.form.description', locale)}
              <Textarea
                className="mt-1 h-16"
                value={draft.description}
                maxLength={500}
                onChange={(e) => patchDraft({ description: e.target.value })}
                placeholder={t('scheduling.rules.form.descriptionPlaceholder', locale)}
              />
            </label>
            {!isEdit && (
              <label className="col-span-2 flex items-center gap-2 text-sm">
                <Switch
                  checked={draft.isDefault}
                  onCheckedChange={(checked) => patchDraft({ isDefault: checked })}
                />
                <span>{t('scheduling.rules.form.setAsDefault', locale)}</span>
              </label>
            )}
          </div>
        </section>

        <section className="rounded-xl border border-border bg-white p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">{t('scheduling.rules.section.targets', locale)}</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {t('scheduling.rules.section.targetsDesc', locale)}
              </p>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <Switch
                checked={draft.targetsEnabled}
                onCheckedChange={(checked) => patchDraft({ targetsEnabled: checked })}
              />
              <span>{t('scheduling.rules.form.targetsEnabled', locale)}</span>
            </label>
          </div>
          {!draft.targetsEnabled && (
            <p className="mt-2 text-xs text-amber-800">
              {t('scheduling.rules.form.targetsDisabledHint', locale)}
            </p>
          )}
          <div className={`mt-4 overflow-auto ${draft.targetsEnabled ? '' : 'pointer-events-none opacity-50'}`}>
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground">
                  <th className="border border-border bg-muted/40 px-2 py-2 text-left font-medium">
                    {t('scheduling.rules.form.shiftCol', locale)}
                  </th>
                  {WEEKDAY_KEYS.map((w) => (
                    <th
                      key={w}
                      className="border border-border bg-muted/40 px-2 py-2 text-center font-medium"
                    >
                      {t(`scheduling.board.weekday.${w}`, locale)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {enabledShifts.map((shift) => {
                  const band = draft.targets[String(shift.id)] ?? emptyTargetBand()
                  return (
                    <tr key={shift.id}>
                      <td className="border border-border px-2 py-1.5 align-top">
                        <span
                          className="inline-flex rounded px-2 py-0.5 text-xs font-medium text-white"
                          style={{ background: shift.color }}
                        >
                          {shift.name}
                        </span>
                        <div className="mt-2 space-y-1 text-[10px] text-muted-foreground">
                          <div>{t('scheduling.rules.form.targetMin', locale)}</div>
                          <div>{t('scheduling.rules.form.targetGoal', locale)}</div>
                          <div>{t('scheduling.rules.form.targetMax', locale)}</div>
                        </div>
                      </td>
                      {WEEKDAY_KEYS.map((_, dayIndex) => (
                        <td key={dayIndex} className="border border-border px-1.5 py-1.5 text-center align-top">
                          <div className="flex flex-col items-center gap-1">
                            {(['min', 'target', 'max'] as const).map((field) => (
                              <span
                                key={field}
                                className="inline-flex h-7 min-w-[3rem] items-center justify-center gap-0.5 rounded-md border border-border px-1 tabular-nums focus-within:border-primary"
                              >
                                <input
                                  type="number"
                                  min={0}
                                  max={99}
                                  disabled={!draft.targetsEnabled}
                                  className="w-7 bg-transparent text-center text-xs outline-none"
                                  value={band[field][dayIndex] ?? 0}
                                  onChange={(e) =>
                                    setTargetField(
                                      shift.id,
                                      dayIndex,
                                      field,
                                      Math.max(0, Math.min(99, Number(e.target.value) || 0)),
                                    )
                                  }
                                />
                              </span>
                            ))}
                          </div>
                        </td>
                      ))}
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {enabledShifts.length === 0 && (
              <p className="py-4 text-center text-xs text-muted-foreground">
                {t('scheduling.board.noEnabledShifts', locale)}
              </p>
            )}
          </div>
        </section>

        <section className="rounded-xl border border-border bg-white p-5">
          <h2 className="text-sm font-semibold">{t('scheduling.rules.section.constraints', locale)}</h2>
          <p className="mt-1 text-xs text-muted-foreground">
            {t('scheduling.rules.section.constraintsDesc', locale)}
          </p>
          <div className="mt-4 space-y-2">
            {CONSTRAINT_DEFS.map((def) => {
              const cfg = draft.constraints[def.key]
              if (!cfg) return null
              return (
                <div
                  key={def.key}
                  className={`flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2.5 text-sm ${
                    cfg.enabled ? 'border-border bg-white' : 'border-border/60 bg-muted/20 opacity-70'
                  }`}
                >
                  <Switch
                    checked={cfg.enabled}
                    onCheckedChange={(checked) => setConstraint(def.key, { enabled: checked })}
                    aria-label={t(`scheduling.rules.constraint.${def.key}`, locale)}
                  />
                  <span className="w-36 shrink-0 font-medium">
                    {t(`scheduling.rules.constraint.${def.key}`, locale)}
                  </span>

                  {def.param ? (
                    <div className="flex items-center gap-1.5 text-muted-foreground">
                      <span className="text-xs">{t(`scheduling.rules.constraint.prefix.${def.key}`, locale)}</span>
                      <Input
                        type="number"
                        className="h-8 w-16 text-center tabular-nums"
                        min={def.param.min}
                        max={def.param.max}
                        disabled={!cfg.enabled}
                        value={cfg.value ?? def.param.defaultValue}
                        onChange={(e) => {
                          const raw = Number(e.target.value) || 0
                          const value = Math.max(def.param!.min, Math.min(def.param!.max, raw))
                          setConstraint(def.key, { value })
                        }}
                      />
                      <span className="text-xs">{t(`scheduling.rules.constraint.suffix.${def.key}`, locale)}</span>
                      <span className="ml-1 text-[10px] text-muted-foreground/80">
                        {def.param.min}–{def.param.max}
                      </span>
                    </div>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      {t(`scheduling.rules.constraint.noParam`, locale)}
                    </span>
                  )}

                  <div className="ml-auto flex items-center gap-1 rounded-md border border-border p-0.5 text-[11px]">
                    <button
                      type="button"
                      disabled={!def.levelEditable}
                      className={`rounded px-2 py-0.5 ${
                        cfg.level === 'hard'
                          ? 'bg-red-50 font-medium text-red-700'
                          : 'text-muted-foreground'
                      } ${def.levelEditable ? '' : 'cursor-not-allowed opacity-60'}`}
                      onClick={() => setConstraint(def.key, { level: 'hard' })}
                    >
                      {t('scheduling.rules.constraint.hard', locale)}
                    </button>
                    <button
                      type="button"
                      disabled={!def.levelEditable}
                      className={`rounded px-2 py-0.5 ${
                        cfg.level === 'soft'
                          ? 'bg-amber-50 font-medium text-amber-800'
                          : 'text-muted-foreground'
                      } ${def.levelEditable ? '' : 'cursor-not-allowed opacity-60'}`}
                      onClick={() => setConstraint(def.key, { level: 'soft' })}
                    >
                      {t('scheduling.rules.constraint.soft', locale)}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        </section>

        <section className="rounded-xl border border-border bg-white p-5">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-sm font-semibold">{t('scheduling.rules.section.templates', locale)}</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                {t('scheduling.rules.section.templatesDesc', locale)}
              </p>
            </div>
            <Button size="sm" onClick={() => setTemplateDialog({ open: true, template: null })}>
              <IconPlus size={14} />
              {t('scheduling.rules.template.new', locale)}
            </Button>
          </div>
          <div className="mt-4 space-y-2">
            {draft.templates.length === 0 ? (
              <p className="py-3 text-center text-xs text-muted-foreground">
                {t('scheduling.rules.template.empty', locale)}
              </p>
            ) : (
              draft.templates.map((tpl) => (
                <div key={tpl.id} className="rounded-lg border border-border px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium">{tpl.name}</span>
                        {tpl.is_default && (
                          <span className="rounded-md bg-primary/10 px-2 py-0.5 text-[11px] text-primary">
                            {t('scheduling.rules.template.defaultBadge', locale)}
                          </span>
                        )}
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-1 text-xs">
                        {tpl.days.map((d, i) => (
                          <span key={i} className="inline-flex items-center gap-1">
                            {i > 0 ? <span className="text-muted-foreground">→</span> : null}
                            <span
                              className={`rounded px-2 py-0.5 ${
                                d.kind === 'off'
                                  ? 'bg-muted text-muted-foreground'
                                  : 'bg-primary/10 text-primary'
                              }`}
                            >
                              {d.kind === 'off'
                                ? t('scheduling.rules.template.kindOff', locale)
                                : (enabledShifts.find((s) => s.id === d.shift_id)?.name ?? '—')}
                            </span>
                          </span>
                        ))}
                      </div>
                      <div className="mt-1.5 text-[11px] text-muted-foreground">
                        {t('scheduling.rules.template.cycle', locale, { count: tpl.days.length })}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setTemplateDialog({ open: true, template: tpl })}
                      >
                        {t('scheduling.rules.edit', locale)}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:text-destructive"
                        onClick={() => removeTemplate(tpl.id)}
                      >
                        <IconTrash size={14} />
                      </Button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      <RotationTemplateDialog
        open={templateDialog.open}
        template={templateDialog.template}
        shifts={enabledShifts}
        onClose={() => setTemplateDialog({ open: false, template: null })}
        onSave={saveTemplate}
      />

      <ConfirmDialog
        open={leaveConfirm}
        title={t('scheduling.rules.leaveConfirm.title', locale)}
        message={t('scheduling.rules.leaveConfirm.message', locale)}
        confirmLabel={t('scheduling.rules.leaveConfirm.confirm', locale)}
        cancelLabel={t('scheduling.form.cancel', locale)}
        variant="destructive"
        onCancel={() => setLeaveConfirm(false)}
        onConfirm={() => router.push('/scheduling/rules')}
      />
    </div>
  )
}
