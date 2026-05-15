'use client'

import { useEffect, useMemo, useState } from 'react'
import { IconLoader2 } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { UnifiedField } from '@/models/field-definition'
import type { CsSummaryInteractionRule, CsSummaryUsageField } from '@/models/session-summary'
import { useSessionSummaryUsage, useUpdateSessionSummaryFieldValue } from '@/service/use-session-summary'
import { FieldValueDisplay } from '@/app/components/features/field-system/field-value-display'
import { UnifiedFieldValueEditor } from '@/app/components/features/field-system/field-value-editor'
import { FieldType } from '@/types/field-enums'

type FieldState = 'hidden' | 'required' | 'optional' | 'readonly'

type Props = {
  conversationId: number
  onDirtyChange?: (dirty: boolean) => void
}

const INSTANT_SAVE_FIELD_TYPES = new Set<FieldType>([
  FieldType.SINGLE_SELECT,
  FieldType.MULTI_SELECT,
  FieldType.SINGLE_SELECT_TREE,
  FieldType.MULTI_SELECT_TREE,
  FieldType.FILE,
])

export function SessionSummaryFields({ conversationId, onDirtyChange }: Props) {
  const { locale } = useLocaleStore()
  const summaryQuery = useSessionSummaryUsage(conversationId)
  const updateField = useUpdateSessionSummaryFieldValue()
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [draftValue, setDraftValue] = useState<unknown>(null)
  const [fieldError, setFieldError] = useState<string | null>(null)

  const values = summaryQuery.data?.values ?? {}
  const states = useMemo(
    () => calculateStates(summaryQuery.data?.fields ?? [], summaryQuery.data?.rules ?? [], values),
    [summaryQuery.data?.fields, summaryQuery.data?.rules, values],
  )
  const dirty = !!editingKey || updateField.isPending || !!fieldError

  useEffect(() => {
    onDirtyChange?.(dirty)
  }, [dirty, onDirtyChange])

  if (summaryQuery.isLoading) {
    return <PanelStateMessage>{t('ws.summary.loading', locale)}</PanelStateMessage>
  }

  if (summaryQuery.isError) {
    return (
      <div className="rounded-lg border border-border bg-background/70 px-3 py-4 text-center">
        <p className="text-xs text-destructive">{t('ws.summary.loadFailed', locale)}</p>
        <button type="button" onClick={() => void summaryQuery.refetch()} className="mt-2 text-xs font-medium text-primary hover:underline">
          {t('ws.chat.retry', locale)}
        </button>
      </div>
    )
  }

  const rows = (summaryQuery.data?.fields ?? [])
    .map((configField) => ({ configField, field: toUnifiedField(configField), state: states[getConfigFieldKey(configField)] ?? 'optional' }))
    .filter((row): row is { configField: CsSummaryUsageField; field: UnifiedField; state: FieldState } => !!row.field && row.state !== 'hidden')

  if (rows.length === 0) {
    return <PanelStateMessage>{t('ws.summary.empty', locale)}</PanelStateMessage>
  }

  const cancelEdit = () => {
    setEditingKey(null)
    setDraftValue(null)
    setFieldError(null)
  }

  const saveEdit = async (configField: CsSummaryUsageField, submittedValue: unknown = draftValue) => {
    const key = getConfigFieldKey(configField)
    const originalValue = values[key] ?? null
    if (areValuesEqual(originalValue, submittedValue)) {
      cancelEdit()
      return
    }
    if (states[key] === 'required' && isEmptyValue(submittedValue)) {
      setFieldError(t('ws.chat.fieldRequired', locale))
      return
    }
    try {
      await updateField.mutateAsync({
        conversationId,
        data: {
          field_definition_id: configField.field_definition_id,
          field_key: configField.field_key,
          value: normalizeEmptyValue(submittedValue),
        },
      })
      cancelEdit()
    } catch {
      setFieldError(t('ws.summary.saveFailed', locale))
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
            saving={editing && updateField.isPending}
            error={editing ? fieldError : null}
            locale={locale}
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
  locale,
  onEdit,
  onChange,
  onCancel,
  onSave,
  onSaveValue,
}: {
  field: UnifiedField
  state: FieldState
  value: unknown
  editing: boolean
  saving: boolean
  error: string | null
  locale: Locale
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
          aria-label={editable ? `${t('ws.chat.editField', locale)} ${field.name}` : field.name}
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

function getConfigFieldKey(field: CsSummaryUsageField): string {
  return field.field_definition_id != null ? String(field.field_definition_id) : String(field.field_key)
}

function toUnifiedField(configField: CsSummaryUsageField): UnifiedField | null {
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

function calculateStates(fields: CsSummaryUsageField[], rules: CsSummaryInteractionRule[], values: Record<string, unknown>): Record<string, FieldState> {
  const states = Object.fromEntries(fields.map((field) => [getConfigFieldKey(field), 'optional' as FieldState]))
  for (const rule of rules) {
    const checks = (rule.conditions ?? []).map((condition) => {
      const key = condition.field_key ? String(condition.field_key) : String(condition.field_id ?? '')
      return matchesCondition(values[key], String(condition.operator ?? 'eq'), condition.value)
    })
    const matched = checks.length === 0 || (rule.condition_logic === 'or' ? checks.some(Boolean) : checks.every(Boolean))
    if (!matched) continue
    for (const action of rule.actions ?? []) {
      const key = action.target_field_key ? String(action.target_field_key) : String(action.target_field_id ?? '')
      const state = action.state
      if (key in states && (state === 'hidden' || state === 'required' || state === 'optional' || state === 'readonly')) {
        states[key] = state
      }
    }
  }
  return states
}

function matchesCondition(actual: unknown, operator: string, expected: unknown): boolean {
  const op = operator.toLowerCase()
  if (op === 'eq' || op === 'equals' || op === '=') return JSON.stringify(actual) === JSON.stringify(expected)
  if (op === 'ne' || op === 'not_equals' || op === '!=') return JSON.stringify(actual) !== JSON.stringify(expected)
  if (op === 'is_empty' || op === 'is_null') return isEmptyValue(actual)
  if (op === 'is_not_empty' || op === 'is_not_null') return !isEmptyValue(actual)
  if (op === 'contains' || op === 'like') return Array.isArray(actual) ? actual.includes(expected) : String(actual ?? '').includes(String(expected ?? ''))
  return false
}

function normalizeEmptyValue(value: unknown): unknown {
  return value === '' ? null : value
}

function isEmptyValue(value: unknown): boolean {
  return value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0)
}

function areValuesEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(normalizeEmptyValue(a)) === JSON.stringify(normalizeEmptyValue(b))
}
