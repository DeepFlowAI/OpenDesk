'use client'

import { useEffect, useMemo, useState } from 'react'
import { IconLoader2 } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import type { FdFieldDefinition, UnifiedField } from '@/models/field-definition'
import { FieldValueDisplay } from '@/app/components/features/field-system/field-value-display'
import { UnifiedFieldValueEditor } from '@/app/components/features/field-system/field-value-editor'
import { FieldType } from '@/types/field-enums'

export type SummaryFieldState = 'hidden' | 'required' | 'optional' | 'readonly'

export type SummaryUsageConfigField = {
  id: number
  config_id: number
  field_definition_id: number | null
  field_key: string | null
  sort_order: number
  is_active: boolean
  field_definition: FdFieldDefinition | null
}

export type SummaryUsageRule = {
  condition_logic: string
  conditions: Record<string, unknown>[]
  actions: Record<string, unknown>[]
}

export type SummaryUsageFieldValueUpdate = {
  field_definition_id?: number | null
  field_key?: string | null
  value: unknown
}

type SummaryUsageTexts = {
  loading: string
  loadFailed: string
  empty: string
  retry: string
  fieldRequired: string
  saveFailed: string
  editField: string
  unavailable?: string
}

type Props = {
  fields?: SummaryUsageConfigField[]
  rules?: SummaryUsageRule[]
  values?: Record<string, unknown>
  isLoading?: boolean
  isError?: boolean
  isSaving?: boolean
  texts: SummaryUsageTexts
  onRetry?: () => void
  onSaveField: (data: SummaryUsageFieldValueUpdate) => Promise<unknown>
  onDirtyChange?: (dirty: boolean) => void
}

const INSTANT_SAVE_FIELD_TYPES = new Set<FieldType>([
  FieldType.SINGLE_SELECT,
  FieldType.MULTI_SELECT,
  FieldType.SINGLE_SELECT_TREE,
  FieldType.MULTI_SELECT_TREE,
  FieldType.FILE,
])

export function SummaryUsageFields({
  fields = [],
  rules = [],
  values = {},
  isLoading = false,
  isError = false,
  isSaving = false,
  texts,
  onRetry,
  onSaveField,
  onDirtyChange,
}: Props) {
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [draftValue, setDraftValue] = useState<unknown>(null)
  const [fieldError, setFieldError] = useState<string | null>(null)

  const states = useMemo(() => calculateSummaryFieldStates(fields, rules, values), [fields, rules, values])
  const dirty = !!editingKey || isSaving || !!fieldError

  useEffect(() => {
    onDirtyChange?.(dirty)
  }, [dirty, onDirtyChange])

  if (texts.unavailable) {
    return <PanelStateMessage>{texts.unavailable}</PanelStateMessage>
  }

  if (isLoading) {
    return <PanelStateMessage>{texts.loading}</PanelStateMessage>
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-border bg-background/70 px-3 py-4 text-center">
        <p className="text-xs text-destructive">{texts.loadFailed}</p>
        {onRetry && (
          <button type="button" onClick={onRetry} className="mt-2 text-xs font-medium text-primary hover:underline">
            {texts.retry}
          </button>
        )}
      </div>
    )
  }

  const rows = fields
    .map((configField) => ({ configField, field: toUnifiedField(configField), state: states[getConfigFieldKey(configField)] ?? 'optional' }))
    .filter((row): row is { configField: SummaryUsageConfigField; field: UnifiedField; state: SummaryFieldState } => !!row.field && row.state !== 'hidden')

  if (rows.length === 0) {
    return <PanelStateMessage>{texts.empty}</PanelStateMessage>
  }

  const cancelEdit = () => {
    setEditingKey(null)
    setDraftValue(null)
    setFieldError(null)
  }

  const saveEdit = async (configField: SummaryUsageConfigField, submittedValue: unknown = draftValue) => {
    const key = getConfigFieldKey(configField)
    const originalValue = values[key] ?? null
    if (areValuesEqual(originalValue, submittedValue)) {
      cancelEdit()
      return
    }
    if (states[key] === 'required' && isEmptyValue(submittedValue)) {
      setFieldError(texts.fieldRequired)
      return
    }
    try {
      await onSaveField({
        field_definition_id: configField.field_definition_id,
        field_key: configField.field_key,
        value: normalizeEmptyValue(submittedValue),
      })
      cancelEdit()
    } catch {
      setFieldError(texts.saveFailed)
    }
  }

  return (
    <div className="flex flex-col gap-[14px]">
      {rows.map(({ configField, field, state }) => {
        const key = getConfigFieldKey(configField)
        const editing = editingKey === key
        return (
          <SummaryFieldRow
            key={key}
            field={field}
            state={state}
            value={editing ? draftValue : values[key] ?? null}
            editing={editing}
            saving={editing && isSaving}
            error={editing ? fieldError : null}
            editFieldText={texts.editField}
            onEdit={() => {
              if (state === 'readonly') return
              setEditingKey(key)
              setDraftValue(values[key] ?? null)
              setFieldError(null)
            }}
            onChange={setDraftValue}
            onCancel={cancelEdit}
            onSave={() => saveEdit(configField)}
            onSaveValue={(value) => saveEdit(configField, value)}
          />
        )
      })}
      <div aria-hidden className="h-[200px] shrink-0" />
    </div>
  )
}

function SummaryFieldRow({
  field,
  state,
  value,
  editing,
  saving,
  error,
  editFieldText,
  onEdit,
  onChange,
  onCancel,
  onSave,
  onSaveValue,
}: {
  field: UnifiedField
  state: SummaryFieldState
  value: unknown
  editing: boolean
  saving: boolean
  error: string | null
  editFieldText: string
  onEdit: () => void
  onChange: (value: unknown) => void
  onCancel: () => void
  onSave: () => void
  onSaveValue: (value: unknown) => void
}) {
  const shouldSaveOnChange = INSTANT_SAVE_FIELD_TYPES.has(field.field_type)
  const editable = state !== 'readonly'

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-1.5">
        <span className="text-[12px] text-muted-foreground">
          {field.name}
          {state === 'required' && <span className="ml-0.5 text-destructive">*</span>}
        </span>
      </div>
      {editing ? (
        <div
          onBlurCapture={(event) => {
            if (event.currentTarget.contains(event.relatedTarget as Node | null)) return
            if (field.field_type === FieldType.FILE) return
            void onSave()
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault()
              onCancel()
            }
            if (event.key === 'Enter' && field.field_type !== FieldType.MULTI_LINE_TEXT && !INSTANT_SAVE_FIELD_TYPES.has(field.field_type)) {
              event.preventDefault()
              void onSave()
            }
          }}
        >
          <div className="relative">
            <UnifiedFieldValueEditor
              field={field}
              value={value}
              onChange={(nextValue) => {
                onChange(nextValue)
                if (shouldSaveOnChange) void onSaveValue(nextValue)
              }}
              disabled={saving}
              className="min-h-8 text-[13px]"
              autoFocus
            />
            {saving && <IconLoader2 size={14} className="absolute right-2 top-2.5 animate-spin text-muted-foreground" />}
          </div>
          {error && <p className="mt-1 text-xs text-destructive">{error}</p>}
        </div>
      ) : (
        <button
          type="button"
          onClick={onEdit}
          disabled={!editable}
          className={cn(
            'min-h-5 max-w-full rounded-sm text-left text-[13px] text-foreground outline-none',
            editable && 'cursor-text hover:bg-black/[0.04] focus-visible:ring-2 focus-visible:ring-ring',
            !editable && 'cursor-default text-muted-foreground',
          )}
          aria-label={editable ? `${editFieldText} ${field.name}` : field.name}
        >
          <FieldValueDisplay
            fieldType={field.field_type}
            value={value}
            typeConfig={field.type_config ?? {}}
            options={field.options}
            treeNodes={field.tree_nodes}
            className="break-words text-[13px]"
          />
        </button>
      )}
    </div>
  )
}

function PanelStateMessage({ children }: { children: string }) {
  return (
    <div className="rounded-lg border border-border bg-background/70 px-3 py-4 text-center">
      <p className="text-xs text-muted-foreground">{children}</p>
    </div>
  )
}

function getConfigFieldKey(field: SummaryUsageConfigField): string {
  return field.field_definition_id != null ? String(field.field_definition_id) : String(field.field_key)
}

function toUnifiedField(configField: SummaryUsageConfigField): UnifiedField | null {
  const definition = configField.field_definition
  if (!definition) return null
  return {
    key: null,
    id: definition.id,
    domain: definition.domain,
    source: definition.source,
    name: definition.name,
    description: definition.description,
    help_text: definition.help_text,
    field_type: definition.field_type,
    type_config: definition.type_config,
    applicable_modules: definition.applicable_modules,
    slot_column: definition.slot_column,
    show_in_workspace: definition.show_in_workspace,
    sort_order: configField.sort_order,
    status: definition.status,
    options: definition.options,
    tree_nodes: definition.tree_nodes,
    created_at: definition.created_at,
    updated_at: definition.updated_at,
  }
}

export function calculateSummaryFieldStates(
  fields: SummaryUsageConfigField[],
  rules: SummaryUsageRule[],
  values: Record<string, unknown>,
): Record<string, SummaryFieldState> {
  const states = Object.fromEntries(fields.map((field) => [getConfigFieldKey(field), 'optional' as SummaryFieldState]))
  for (const rule of rules) {
    const conditions = rule.conditions ?? []
    const checks = conditions.map((condition) =>
      matchesCondition(
        values[getConditionFieldKey(condition)],
        String(condition.operator ?? 'eq'),
        condition.value,
      ),
    )
    const matched = checks.length === 0 || (rule.condition_logic === 'or' ? checks.some(Boolean) : checks.every(Boolean))
    if (!matched) continue
    for (const action of rule.actions ?? []) {
      const key = getActionTargetFieldKey(action)
      const state = action.state
      if (key in states && (state === 'hidden' || state === 'required' || state === 'optional' || state === 'readonly')) {
        states[key] = state
      }
    }
  }
  return states
}

function getConditionFieldKey(condition: Record<string, unknown>): string {
  return getRuleFieldKey(condition, 'field_id', 'field_key', 'field_definition_id')
}

function getActionTargetFieldKey(action: Record<string, unknown>): string {
  return getRuleFieldKey(action, 'target_field_id', 'target_field_key', 'target_field_definition_id')
}

function getRuleFieldKey(
  row: Record<string, unknown>,
  idKey: string,
  keyKey: string,
  aliasIdKey: string,
): string {
  const fieldKey = typeof row[keyKey] === 'string' && row[keyKey] ? row[keyKey] : null
  if (fieldKey) return fieldKey
  const rawId = row[idKey] ?? row[aliasIdKey]
  if (rawId == null || rawId === '') return ''
  return String(rawId)
}

function matchesCondition(actual: unknown, operator: string, expected: unknown): boolean {
  const op = operator.toLowerCase()
  if (op === 'eq' || op === 'equals' || op === '=') return areRawValuesEqual(actual, expected)
  if (op === 'ne' || op === 'not_equals' || op === '!=') return !areRawValuesEqual(actual, expected)
  if (op === 'contains' || op === 'like') {
    if (Array.isArray(actual)) return actual.some((item) => areRawValuesEqual(item, expected))
    return String(actual ?? '').includes(String(expected ?? ''))
  }
  if (op === 'not_contains' || op === 'not_like') {
    if (Array.isArray(actual)) return !actual.some((item) => areRawValuesEqual(item, expected))
    return !String(actual ?? '').includes(String(expected ?? ''))
  }
  if (op === 'starts_with') return String(actual ?? '').startsWith(String(expected ?? ''))
  if (op === 'ends_with') return String(actual ?? '').endsWith(String(expected ?? ''))
  if (op === 'is_empty' || op === 'is_null') return isEmptyValue(actual)
  if (op === 'is_not_empty' || op === 'is_not_null') return !isEmptyValue(actual)
  if (op === 'in') return Array.isArray(expected) ? expected.some((item) => areRawValuesEqual(actual, item)) : false
  if (op === 'not_in') return Array.isArray(expected) ? !expected.some((item) => areRawValuesEqual(actual, item)) : true

  const left = toComparableNumber(actual)
  const right = toComparableNumber(expected)
  if (left == null || right == null) return false
  if (op === 'gt' || op === '>') return left > right
  if (op === 'gte' || op === '>=') return left >= right
  if (op === 'lt' || op === '<') return left < right
  if (op === 'lte' || op === '<=') return left <= right
  return false
}

function toComparableNumber(value: unknown): number | null {
  if (value == null) return null
  const raw = String(value).trim()
  if (!raw) return null
  const number = Number(raw)
  return Number.isFinite(number) ? number : null
}

function normalizeEmptyValue(value: unknown): unknown {
  return value === '' ? null : value
}

function isEmptyValue(value: unknown): boolean {
  if (value === null || value === undefined || value === '') return true
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.keys(value).length === 0
  return false
}

function areValuesEqual(a: unknown, b: unknown): boolean {
  return areRawValuesEqual(normalizeEmptyValue(a), normalizeEmptyValue(b))
}

function areRawValuesEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}
