'use client'

import { useState, useCallback, useMemo } from 'react'
import {
  IconPlus,
  IconPencil,
  IconTrash,
  IconArrowLeft,
  IconX,
} from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import {
  useInteractionRules,
  useCreateInteractionRule,
  useUpdateInteractionRule,
  useDeleteInteractionRule,
} from '@/service/use-interaction-rules'
import type {
  FdInteractionRule,
  InteractionRuleCondition,
  InteractionRuleAction,
} from '@/models/interaction-rule'
import type { UnifiedField } from '@/models/field-definition'
import {
  FilterValueEditor,
  NO_VALUE_OPS,
  operatorsForFieldType,
  valueShape,
} from '@/components/filter'

export type FieldOption = {
  value: string
  label: string
  isSystem: boolean
  field: UnifiedField
}

type Props = {
  layoutId: number
  availableFields: FieldOption[]
}

type DraftRule = {
  id?: number
  name: string
  condition_logic: 'and' | 'or'
  conditions: InteractionRuleCondition[]
  actions: InteractionRuleAction[]
  is_enabled: boolean
}

const EMPTY_CONDITION: InteractionRuleCondition = {
  field_source: 'layout',
  field_id: null,
  field_key: null,
  operator: 'eq',
  value: null,
}

const EMPTY_ACTION: InteractionRuleAction = {
  target_field_id: null,
  target_field_key: null,
  state: 'required',
}

function conditionFieldValue(c: InteractionRuleCondition): string {
  if (c.field_key) return `key:${c.field_key}`
  if (c.field_id) return `def:${c.field_id}`
  return ''
}

function actionFieldValue(a: InteractionRuleAction): string {
  if (a.target_field_key) return `key:${a.target_field_key}`
  if (a.target_field_id) return `def:${a.target_field_id}`
  return ''
}

function parseFieldOption(value: string): { field_key: string | null; field_id: number | null } {
  if (value.startsWith('key:')) return { field_key: value.slice(4), field_id: null }
  if (value.startsWith('def:')) return { field_key: null, field_id: Number(value.slice(4)) }
  return { field_key: null, field_id: null }
}

function normalizeOperator(operator: string): string {
  if (operator === 'equals' || operator === '=') return 'eq'
  if (operator === 'not_equals' || operator === '!=') return 'ne'
  if (operator === 'like') return 'contains'
  if (operator === 'is_null') return 'is_empty'
  if (operator === 'is_not_null') return 'is_not_empty'
  return operator
}

function normalizeCondition(c: InteractionRuleCondition): InteractionRuleCondition {
  const operator = normalizeOperator(c.operator)
  return {
    ...c,
    operator,
    value: NO_VALUE_OPS.has(operator) ? null : c.value,
  }
}

function resolveFieldName(
  key: string | null, id: number | null, fields: FieldOption[],
): string {
  if (key) {
    const opt = fields.find((f) => f.value === `key:${key}`)
    return opt?.label ?? key
  }
  if (id) {
    const opt = fields.find((f) => f.value === `def:${id}`)
    return opt?.label ?? `#${id}`
  }
  return '?'
}

function buildSummary(
  rule: FdInteractionRule, locale: 'zh' | 'en', fields: FieldOption[],
): string {
  const conds = (rule.conditions ?? [])
    .map((c) => {
      const name = resolveFieldName(c.field_key, c.field_id, fields)
      const operator = normalizeOperator(c.operator)
      return `${name} ${t(`tv.op.${operator}`, locale)} ${String(c.value ?? '')}`
    })
    .join(rule.condition_logic === 'and' ? ' AND ' : ' OR ')

  const acts = (rule.actions ?? [])
    .map((a) => {
      const target = resolveFieldName(a.target_field_key, a.target_field_id, fields)
      return `${target} → ${t(`fl.state.${a.state}`, locale)}`
    })
    .join(', ')

  if (!conds && !acts) return '—'
  return `${locale === 'zh' ? '当' : 'When'} ${conds || '...'} → ${acts || '...'}`
}

export function InteractionRulesTab({ layoutId, availableFields }: Props) {
  const { locale } = useLocaleStore()
  const { data, isLoading } = useInteractionRules(layoutId)
  const createMutation = useCreateInteractionRule(layoutId)
  const updateMutation = useUpdateInteractionRule(layoutId)
  const deleteMutation = useDeleteInteractionRule(layoutId)

  const [drawerOpen, setDrawerOpen] = useState(false)
  const [draft, setDraft] = useState<DraftRule | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<FdInteractionRule | null>(null)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const rules = useMemo(() => data?.items ?? [], [data])

  const showToast = useCallback(
    (type: 'success' | 'error', key: string) => {
      setToast({ type, text: t(key, locale) })
      setTimeout(() => setToast(null), 3000)
    },
    [locale]
  )

  const openNewRule = useCallback(() => {
    setDraft({
      name: '',
      condition_logic: 'and',
      conditions: [{ ...EMPTY_CONDITION }],
      actions: [{ ...EMPTY_ACTION }],
      is_enabled: true,
    })
    setDrawerOpen(true)
  }, [])

  const openEditRule = useCallback((rule: FdInteractionRule) => {
    setDraft({
      id: rule.id,
      name: rule.name ?? '',
      condition_logic: rule.condition_logic,
      conditions: rule.conditions?.length ? rule.conditions.map(normalizeCondition) : [{ ...EMPTY_CONDITION }],
      actions: rule.actions?.length ? [...rule.actions] : [{ ...EMPTY_ACTION }],
      is_enabled: rule.is_enabled,
    })
    setDrawerOpen(true)
  }, [])

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false)
    setDraft(null)
  }, [])

  const handleSaveRule = useCallback(async () => {
    if (!draft) return
    try {
      const payload = {
        name: draft.name || null,
        condition_logic: draft.condition_logic,
        conditions: draft.conditions,
        actions: draft.actions,
        is_enabled: draft.is_enabled,
      }
      if (draft.id) {
        await updateMutation.mutateAsync({ id: draft.id, data: payload })
      } else {
        await createMutation.mutateAsync(payload)
      }
      closeDrawer()
      showToast('success', 'fl.saveSuccess')
    } catch {
      showToast('error', 'fl.saveFailed')
    }
  }, [draft, updateMutation, createMutation, closeDrawer, showToast])

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return
    try {
      await deleteMutation.mutateAsync(deleteTarget.id)
      setDeleteTarget(null)
      showToast('success', 'ir.deleteSuccess')
    } catch {
      showToast('error', 'ir.deleteFailed')
    }
  }, [deleteTarget, deleteMutation, showToast])

  const handleToggleEnabled = useCallback(
    async (rule: FdInteractionRule) => {
      try {
        await updateMutation.mutateAsync({
          id: rule.id,
          data: { is_enabled: !rule.is_enabled },
        })
      } catch {
        showToast('error', 'fl.saveFailed')
      }
    },
    [updateMutation, showToast]
  )

  return (
    <div className="relative flex flex-1 flex-col overflow-hidden">
      {/* Toast */}
      {toast && (
        <div
          className={cn(
            'absolute left-1/2 top-4 z-50 -translate-x-1/2 rounded-lg px-4 py-2 text-sm shadow-lg',
            toast.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          )}
        >
          {toast.text}
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center justify-between border-b border-border px-6 py-4">
        <h3 className="text-base font-semibold text-foreground">{t('ir.title', locale)}</h3>
        <button
          onClick={openNewRule}
          className="flex h-9 items-center gap-2 rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80"
        >
          <IconPlus size={16} />
          {t('ir.add', locale)}
        </button>
      </div>

      {/* Rules list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <p className="px-6 py-10 text-sm text-muted-foreground">{t('ir.loading', locale)}</p>
        ) : rules.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-4 py-20">
            <p className="text-sm text-muted-foreground">{t('ir.empty', locale)}</p>
            <button
              onClick={openNewRule}
              className="flex items-center gap-2 text-sm font-medium text-info transition-colors hover:text-info/80"
            >
              <IconPlus size={16} />
              {t('ir.add', locale)}
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <div style={{ minWidth: 600 }}>
              {/* Table header */}
              <div className="flex h-12 items-center gap-4 bg-muted px-6">
                <div className="min-w-0 flex-1">
                  <span className="text-sm font-semibold text-foreground/80">{t('ir.col.summary', locale)}</span>
                </div>
                <div className="w-[80px] shrink-0 text-center">
                  <span className="text-sm font-semibold text-foreground/80">{t('ir.col.enabled', locale)}</span>
                </div>
                <div className="w-[120px] shrink-0 text-right">
                  <span className="text-sm font-semibold text-foreground/80">{t('ir.col.actions', locale)}</span>
                </div>
              </div>

              {/* Table rows */}
              {rules.map((rule) => (
                <div
                  key={rule.id}
                  className="flex h-14 cursor-pointer items-center gap-4 border-t border-border px-6 transition-colors hover:bg-accent/50"
                  onClick={() => openEditRule(rule)}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-foreground">
                      {rule.name && <span className="mr-2 font-medium">{rule.name}</span>}
                      <span className="text-muted-foreground">{buildSummary(rule, locale, availableFields)}</span>
                    </p>
                  </div>
                  <div className="flex w-[80px] shrink-0 items-center justify-center">
                    <button
                      onClick={(e) => { e.stopPropagation(); handleToggleEnabled(rule) }}
                      className={cn(
                        'relative h-5 w-9 rounded-full transition-colors',
                        rule.is_enabled ? 'bg-primary' : 'bg-input'
                      )}
                    >
                      <div
                        className={cn(
                          'absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform',
                          rule.is_enabled ? 'translate-x-[18px]' : 'translate-x-0.5'
                        )}
                      />
                    </button>
                  </div>
                  <div className="flex w-[120px] shrink-0 items-center justify-end gap-2">
                    <button
                      onClick={(e) => { e.stopPropagation(); openEditRule(rule) }}
                      className="text-foreground/80 transition-colors hover:text-foreground"
                    >
                      <IconPencil size={16} />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); setDeleteTarget(rule) }}
                      className="text-foreground/80 transition-colors hover:text-destructive"
                    >
                      <IconTrash size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Edit drawer */}
      {drawerOpen && draft && (
        <RuleEditDrawer
          locale={locale}
          draft={draft}
          setDraft={setDraft}
          onSave={handleSaveRule}
          onClose={closeDrawer}
          isSaving={createMutation.isPending || updateMutation.isPending}
          availableFields={availableFields}
        />
      )}

      {/* Delete confirmation */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-[420px] rounded-xl bg-white p-6">
            <h2 className="text-lg font-semibold text-foreground">{t('ir.delete.title', locale)}</h2>
            <p className="mt-3 text-sm text-muted-foreground">{t('ir.delete.confirm', locale)}</p>
            {deleteTarget.name && (
              <p className="mt-2 text-sm font-medium text-foreground">{deleteTarget.name}</p>
            )}
            <div className="mt-6 flex justify-end gap-3">
              <button
                onClick={() => setDeleteTarget(null)}
                className="h-9 rounded-lg border border-border px-4 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
              >
                {t('ir.delete.cancel', locale)}
              </button>
              <button
                onClick={handleDelete}
                disabled={deleteMutation.isPending}
                className="h-9 rounded-lg bg-destructive px-4 text-sm font-medium text-white transition-colors hover:bg-destructive/80 disabled:opacity-50"
              >
                {deleteMutation.isPending ? '...' : t('ir.delete.ok', locale)}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Rule edit drawer ──

function RuleEditDrawer({
  locale,
  draft,
  setDraft,
  onSave,
  onClose,
  isSaving,
  availableFields,
}: {
  locale: 'zh' | 'en'
  draft: DraftRule
  setDraft: (fn: DraftRule | ((d: DraftRule | null) => DraftRule | null)) => void
  onSave: () => void
  onClose: () => void
  isSaving: boolean
  availableFields: FieldOption[]
}) {
  const updateDraft = useCallback(
    (updater: (prev: DraftRule) => DraftRule) => {
      setDraft((prev: DraftRule | null) => (prev ? updater(prev) : prev))
    },
    [setDraft]
  )

  const stateOptions = [
    { value: 'hidden', label: t('fl.state.hidden', locale) },
    { value: 'required', label: t('fl.state.required', locale) },
    { value: 'optional', label: t('fl.state.optional', locale) },
    { value: 'readonly', label: t('fl.state.readonly', locale) },
  ]

  const fieldByValue = useMemo(() => {
    const m = new Map<string, FieldOption>()
    for (const f of availableFields) m.set(f.value, f)
    return m
  }, [availableFields])

  return (
    <div className="absolute inset-0 z-40 flex justify-end">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30" onClick={onClose} />

      {/* Drawer panel */}
      <div className="relative z-10 flex w-[520px] flex-col bg-white shadow-xl">
        {/* Drawer header */}
        <div className="flex h-[56px] items-center justify-between border-b border-border px-5">
          <div className="flex items-center gap-3">
            <button onClick={onClose} className="text-foreground/80 transition-colors hover:text-foreground">
              <IconArrowLeft size={18} />
            </button>
            <span className="text-sm font-semibold text-foreground">
              {draft.id ? t('ir.drawer.editTitle', locale) : t('ir.drawer.newTitle', locale)}
            </span>
          </div>
          <button
            onClick={onSave}
            disabled={isSaving}
            className="flex h-8 items-center rounded-lg bg-primary px-4 text-sm font-medium text-white transition-colors hover:bg-primary/80 disabled:opacity-50"
          >
            {isSaving ? '...' : t('ir.drawer.save', locale)}
          </button>
        </div>

        {/* Drawer body */}
        <div className="flex-1 overflow-y-auto p-5">
          <div className="flex flex-col gap-5">
            {/* Rule name */}
            <div>
              <label className="mb-1.5 block text-sm font-medium text-foreground/80">
                {t('ir.form.name', locale)}
              </label>
              <input
                type="text"
                value={draft.name}
                onChange={(e) => updateDraft((d) => ({ ...d, name: e.target.value }))}
                placeholder={t('ir.form.name.placeholder', locale)}
                className="h-9 w-full rounded-lg border border-border bg-white px-3 text-sm text-foreground outline-none focus:border-ring"
              />
            </div>

            {/* Condition logic toggle */}
            <div>
              <label className="mb-2 block text-sm font-medium text-foreground/80">
                {t('ir.form.conditionLogic', locale)}
              </label>
              <div className="flex gap-2">
                {(['and', 'or'] as const).map((logic) => (
                  <button
                    key={logic}
                    onClick={() => updateDraft((d) => ({ ...d, condition_logic: logic }))}
                    className={cn(
                      'rounded-md border px-3 py-1 text-sm transition-colors',
                      draft.condition_logic === logic
                        ? 'border-foreground bg-primary font-medium text-white'
                        : 'border-border bg-white text-muted-foreground hover:border-muted-foreground'
                    )}
                  >
                    {t(`ir.form.conditionLogic.${logic}`, locale)}
                  </button>
                ))}
              </div>
            </div>

            {/* Conditions */}
            <div>
              <label className="mb-2 block text-sm font-medium text-foreground/80">
                {t('ir.form.conditions', locale)}
              </label>
              <div className="flex flex-col gap-3">
                {draft.conditions.map((cond, idx) => (
                  <div key={idx} className="flex flex-wrap items-center gap-2">
                    {(() => {
                      const selectedFieldValue = conditionFieldValue(cond)
                      const selectedField = selectedFieldValue ? fieldByValue.get(selectedFieldValue)?.field : undefined
                      const operators = selectedField ? operatorsForFieldType(selectedField.field_type) : []
                      const showValueEditor = !!cond.operator && !NO_VALUE_OPS.has(cond.operator)
                      return (
                        <>
                    <select
                      value={selectedFieldValue}
                      onChange={(e) => {
                        const { field_key, field_id } = parseFieldOption(e.target.value)
                        const nextField = fieldByValue.get(e.target.value)?.field
                        const nextOperators = nextField ? operatorsForFieldType(nextField.field_type) : []
                        updateDraft((d) => ({
                          ...d,
                          conditions: d.conditions.map((c, i) =>
                            i === idx
                              ? {
                                  ...c,
                                  field_key,
                                  field_id,
                                  operator: nextOperators.includes(c.operator) ? c.operator : (nextOperators[0] ?? ''),
                                  value: null,
                                }
                              : c
                          ),
                        }))
                      }}
                      className="h-9 min-w-0 flex-1 rounded-lg border border-border px-2 text-sm outline-none focus:border-ring"
                    >
                      <option value="">{t('ir.form.field.placeholder', locale)}</option>
                      {availableFields.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                    <select
                      value={cond.operator}
                      onChange={(e) => {
                        const op = e.target.value
                        updateDraft((d) => ({
                          ...d,
                          conditions: d.conditions.map((c, i) =>
                            i === idx
                              ? {
                                  ...c,
                                  operator: op,
                                  value: valueShape(op) === valueShape(c.operator) && !NO_VALUE_OPS.has(op) ? c.value : null,
                                }
                              : c
                          ),
                        }))
                      }}
                      disabled={!selectedField}
                      className="h-9 w-[110px] shrink-0 rounded-lg border border-border px-2 text-sm outline-none focus:border-ring disabled:bg-accent disabled:text-muted-foreground"
                    >
                      <option value="">{t('uv.filter.selectOp', locale)}</option>
                      {operators.map((op) => (
                        <option key={op} value={op}>{t(`tv.op.${op}`, locale)}</option>
                      ))}
                    </select>
                    {showValueEditor && (
                      <div className="min-w-[140px] flex-1">
                        <FilterValueEditor
                          field={selectedField}
                          operator={cond.operator}
                          value={cond.value}
                          onChange={(value) =>
                          updateDraft((d) => ({
                            ...d,
                            conditions: d.conditions.map((c, i) =>
                              i === idx ? { ...c, value } : c
                            ),
                          }))
                          }
                        placeholder={t('ir.form.value.placeholder', locale)}
                        />
                      </div>
                    )}
                        </>
                      )
                    })()}
                    <button
                      onClick={() =>
                        updateDraft((d) => ({
                          ...d,
                          conditions: d.conditions.filter((_, i) => i !== idx),
                        }))
                      }
                      className="shrink-0 text-border transition-colors hover:text-muted-foreground"
                    >
                      <IconX size={16} />
                    </button>
                  </div>
                ))}
              </div>
              <button
                onClick={() =>
                  updateDraft((d) => ({
                    ...d,
                    conditions: [...d.conditions, { ...EMPTY_CONDITION }],
                  }))
                }
                className="mt-3 flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-foreground/80 transition-colors hover:border-muted-foreground hover:bg-accent/50"
              >
                <IconPlus size={14} />
                {t('ir.form.addCondition', locale)}
              </button>
            </div>

            {/* Actions */}
            <div>
              <label className="mb-3 block text-sm font-semibold text-foreground">
                {t('ir.form.actions', locale)}
              </label>
              <div className="flex flex-col gap-4">
                {draft.actions.map((act, idx) => (
                  <div key={idx} className="flex flex-col gap-3">
                    <div>
                      <label className="mb-1 block text-sm font-medium text-foreground/80">
                        {t('ir.form.targetField', locale)}
                      </label>
                      <div className="flex items-center gap-2">
                        <select
                          value={actionFieldValue(act)}
                          onChange={(e) => {
                            const { field_key, field_id } = parseFieldOption(e.target.value)
                            updateDraft((d) => ({
                              ...d,
                              actions: d.actions.map((a, i) =>
                                i === idx
                                  ? { ...a, target_field_key: field_key, target_field_id: field_id }
                                  : a
                              ),
                            }))
                          }}
                          className="h-9 min-w-0 flex-1 rounded-lg border border-border px-2 text-sm outline-none focus:border-ring"
                        >
                          <option value="">{t('ir.form.targetField.placeholder', locale)}</option>
                          {availableFields.map((opt) => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                          ))}
                        </select>
                        <button
                          onClick={() =>
                            updateDraft((d) => ({
                              ...d,
                              actions: d.actions.filter((_, i) => i !== idx),
                            }))
                          }
                          className="shrink-0 text-border transition-colors hover:text-muted-foreground"
                        >
                          <IconX size={16} />
                        </button>
                      </div>
                    </div>
                    <div>
                      <label className="mb-1 block text-sm font-medium text-foreground/80">
                        {t('ir.form.targetState', locale)}
                      </label>
                      <select
                        value={act.state}
                        onChange={(e) =>
                          updateDraft((d) => ({
                            ...d,
                            actions: d.actions.map((a, i) =>
                              i === idx
                                ? { ...a, state: e.target.value as InteractionRuleAction['state'] }
                                : a
                            ),
                          }))
                        }
                        className="h-9 w-full rounded-lg border border-border px-2 text-sm outline-none focus:border-ring"
                      >
                        {stateOptions.map((opt) => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                    </div>
                    {idx < draft.actions.length - 1 && <hr className="border-border" />}
                  </div>
                ))}
              </div>
              <button
                onClick={() =>
                  updateDraft((d) => ({
                    ...d,
                    actions: [...d.actions, { ...EMPTY_ACTION }],
                  }))
                }
                className="mt-3 flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-foreground/80 transition-colors hover:border-muted-foreground hover:bg-accent/50"
              >
                <IconPlus size={14} />
                {t('ir.form.addAction', locale)}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
