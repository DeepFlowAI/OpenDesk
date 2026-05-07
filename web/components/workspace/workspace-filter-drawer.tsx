'use client'

import { useState, useCallback, useMemo } from 'react'
import { IconPlus, IconTrash } from '@tabler/icons-react'
import { t } from '@/utils/i18n'
import type { Locale } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import type { UnifiedField } from '@/models/field-definition'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import {
  FilterValueEditor,
  NO_VALUE_OPS,
  isConditionValueComplete,
  operatorsForFieldType,
  valueShape,
  type FilterConditionItem,
} from '@/components/filter'

export type { FilterConditionItem } from '@/components/filter'

// ── Field uid (align with admin user-views) ──

function fieldUid(f: UnifiedField): string {
  if (f.id != null) return `id:${f.id}`
  if (f.key != null) return `key:${f.key}`
  return ''
}

function conditionFieldUid(c: FilterConditionItem): string {
  if (c.field_id != null) return `id:${c.field_id}`
  if (c.field_key != null) return `key:${c.field_key}`
  return ''
}

function parseUidToConditionPatch(uid: string): Pick<FilterConditionItem, 'field_id' | 'field_key'> {
  if (uid.startsWith('id:')) return { field_id: Number(uid.slice(3)), field_key: null }
  if (uid.startsWith('key:')) return { field_id: null, field_key: uid.slice(4) }
  return { field_id: null, field_key: null }
}

export type WorkspaceFilterDrawerProps = {
  locale: Locale
  fields: UnifiedField[]
  conditions: FilterConditionItem[]
  conditionLogic: 'and' | 'or'
  onApply: (conditions: FilterConditionItem[], logic: 'and' | 'or') => void
  onClose: () => void
}

export function WorkspaceFilterDrawer({
  locale,
  fields,
  conditions,
  conditionLogic,
  onApply,
  onClose,
}: WorkspaceFilterDrawerProps) {
  const [draft, setDraft] = useState<FilterConditionItem[]>(
    conditions.length > 0 ? conditions.map((c) => ({ ...c })) : [],
  )
  const [logic, setLogic] = useState<'and' | 'or'>(conditionLogic)

  const fieldByUid = useMemo(() => {
    const m = new Map<string, UnifiedField>()
    for (const f of fields) {
      const uid = fieldUid(f)
      if (uid) m.set(uid, f)
    }
    return m
  }, [fields])

  const addCondition = useCallback(() => {
    setDraft((prev) => [...prev, { field_id: null, field_key: null, operator: '', value: null }])
  }, [])

  const removeCondition = useCallback((index: number) => {
    setDraft((prev) => prev.filter((_, i) => i !== index))
  }, [])

  const updateConditionField = useCallback((idx: number, uid: string) => {
    setDraft((prev) => {
      const next = [...prev]
      const patch = parseUidToConditionPatch(uid)
      next[idx] = { ...next[idx], ...patch, operator: '', value: null }
      return next
    })
  }, [])

  const updateConditionOperator = useCallback((idx: number, operator: string) => {
    setDraft((prev) => {
      const next = [...prev]
      const prevShape = valueShape(next[idx].operator)
      const nextShape = valueShape(operator)
      const resetValue = nextShape === 'none' || nextShape !== prevShape
      next[idx] = {
        ...next[idx],
        operator,
        value: resetValue ? null : next[idx].value,
      }
      return next
    })
  }, [])

  const updateConditionValue = useCallback((idx: number, value: unknown) => {
    setDraft((prev) => {
      const next = [...prev]
      next[idx] = { ...next[idx], value: value as FilterConditionItem['value'] }
      return next
    })
  }, [])

  const handleConfirm = useCallback(() => {
    const valid = draft.filter((c) => {
      const hasField = c.field_id != null || c.field_key != null
      if (!hasField || !c.operator) return false
      return isConditionValueComplete(c.operator, c.value)
    })
    onApply(valid, logic)
    onClose()
  }, [draft, logic, onApply, onClose])

  const isZh = locale === 'zh'

  return (
    <Sheet open onOpenChange={(open) => { if (!open) onClose() }}>
      <SheetContent
        side="right"
        className="flex flex-col gap-0 p-0 data-[side=right]:w-full sm:data-[side=right]:w-[560px] data-[side=right]:sm:max-w-[560px]"
        overlayClassName="supports-backdrop-filter:backdrop-blur-none"
        showCloseButton={false}
      >
        <SheetHeader className="flex h-14 shrink-0 flex-row items-center justify-between border-b border-border bg-white px-5 py-0">
          <SheetTitle className="text-base font-semibold">
            {isZh ? '筛选' : 'Filter'}
          </SheetTitle>
          <button
            type="button"
            onClick={handleConfirm}
            className="flex h-9 shrink-0 items-center rounded-lg bg-[#252525] px-4 text-sm font-medium text-white transition-colors hover:bg-[#252525]/90"
          >
            {isZh ? '确定' : 'Confirm'}
          </button>
        </SheetHeader>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3">
          <div className="flex flex-col gap-2">
            <div className="flex rounded-lg bg-muted p-0.5">
              {(['and', 'or'] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setLogic(mode)}
                  className={cn(
                    'flex-1 rounded-md px-3 py-1.5 text-[13px] transition-colors',
                    logic === mode
                      ? 'border border-border bg-white font-medium text-foreground/80'
                      : 'text-muted-foreground',
                  )}
                >
                  {t(`uv.filter.${mode}`, locale)}
                  {mode === 'and' ? ' (AND)' : ' (OR)'}
                </button>
              ))}
            </div>

            {draft.length > 0 && (
            <div className="overflow-visible rounded-lg border border-border">
              {draft.map((cond, idx) => {
                const uid = conditionFieldUid(cond)
                const field = uid ? fieldByUid.get(uid) : undefined
                const ops = field ? operatorsForFieldType(field.field_type) : []
                const hasField = !!uid
                const showValueEditor = !!cond.operator && !NO_VALUE_OPS.has(cond.operator)
                return (
                  <div
                    key={idx}
                    className="flex flex-wrap items-center gap-2.5 border-b border-border px-3 py-2 last:border-b-0"
                  >
                    <select
                      value={uid}
                      onChange={(e) => updateConditionField(idx, e.target.value)}
                      className="h-9 min-w-[120px] flex-1 rounded-md border border-border bg-white px-3 text-sm text-foreground outline-none"
                    >
                      <option value="">{t('uv.filter.selectField', locale)}</option>
                      {fields.map((f) => {
                        const fuid = fieldUid(f)
                        if (!fuid) return null
                        return (
                          <option key={fuid} value={fuid}>
                            {f.name}
                          </option>
                        )
                      })}
                    </select>

                    <select
                      value={cond.operator}
                      onChange={(e) => updateConditionOperator(idx, e.target.value)}
                      className="h-9 min-w-[100px] flex-1 rounded-md border border-border bg-white px-3 text-sm text-foreground outline-none disabled:bg-accent disabled:text-muted-foreground"
                      disabled={!hasField}
                    >
                      <option value="">{t('uv.filter.selectOp', locale)}</option>
                      {ops.map((op) => (
                        <option key={op} value={op}>
                          {t(`uv.op.${op}`, locale)}
                        </option>
                      ))}
                    </select>

                    {showValueEditor && (
                      <div className="min-w-[140px] flex-[2]">
                        <FilterValueEditor
                          field={field}
                          operator={cond.operator}
                          value={cond.value}
                          onChange={(v) => updateConditionValue(idx, v)}
                          placeholder={t('uv.filter.valuePlaceholder', locale)}
                        />
                      </div>
                    )}

                    <button
                      type="button"
                      onClick={() => removeCondition(idx)}
                      className="ml-auto shrink-0 text-muted-foreground hover:text-red-600"
                    >
                      <IconTrash size={16} />
                    </button>
                  </div>
                )
              })}
            </div>
            )}

            <button
              type="button"
              onClick={addCondition}
              className="flex h-9 w-fit items-center gap-1.5 rounded-lg border border-border px-3.5 text-sm font-medium text-foreground/80 transition-colors hover:bg-accent"
            >
              <IconPlus size={16} />
              {t('uv.filter.add', locale)}
            </button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
