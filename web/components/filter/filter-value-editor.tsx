'use client'

import { useMemo } from 'react'
import { cn } from '@/lib/utils'
import { DateInput, DateTimeInput, TimeInput } from '@/components/ui/time-input'
import { TreeSelectEditor } from '@/app/components/features/field-system/tree-select-editor'
import { OrganizationSelectEditor } from '@/app/components/features/field-system/field-value-editor'
import { FieldType } from '@/types/field-enums'
import type { UnifiedField } from '@/models/field-definition'
import { OptionComboBox } from './option-combo-box'
import { NO_VALUE_OPS, valueShape } from './filter-operators'
import { UserSelect } from '@/app/components/features/ticket/user-select'
import { EmployeeSelect } from '@/app/components/features/ticket/employee-select'
import { EmployeeGroupSelect } from '@/app/components/features/ticket/employee-group-select'

export type FilterValueEditorProps = {
  /** Currently selected field; undefined means no field picked yet. */
  field: UnifiedField | undefined
  /** Current operator, e.g. 'eq', 'in', 'is_empty'. */
  operator: string
  /** Current value; shape depends on field_type + operator. */
  value: unknown
  onChange: (v: unknown) => void
  placeholder?: string
  disabled?: boolean
  className?: string
}

const inputClass =
  'h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm text-foreground outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30'

function toNumericUserId(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

/**
 * Single source of truth for rendering the "value" input in a filter
 * condition row. Selects a concrete control based on the field's
 * `field_type` and the current `operator`.
 *
 * Consumers:
 *   - web/components/workspace/workspace-filter-drawer.tsx (all 3 domains)
 *   - web/app/(main)/user-views/page.tsx        FilterTab
 *   - web/app/(main)/organization-views/page.tsx FilterTab
 *   - web/app/(main)/ticket-views/page.tsx       FilterTab
 */
export function FilterValueEditor({
  field,
  operator,
  value,
  onChange,
  placeholder,
  disabled,
  className,
}: FilterValueEditorProps) {
  const shape = valueShape(operator)

  const safePlaceholder = placeholder ?? ''

  const numberStep = useMemo(() => {
    if (!field || field.field_type !== FieldType.NUMBER) return 1
    const decimals = (field.type_config?.decimal_places as number | undefined) ?? 0
    return decimals > 0 ? 1 / Math.pow(10, decimals) : 1
  }, [field])

  if (!field || !operator) return null
  if (shape === 'none' || NO_VALUE_OPS.has(operator)) return null

  switch (field.field_type) {
    case FieldType.SINGLE_LINE_TEXT:
    case FieldType.MULTI_LINE_TEXT:
    case FieldType.RICH_TEXT:
    case FieldType.EMAIL:
    case FieldType.PHONE:
    case FieldType.URL:
      return (
        <input
          type={
            field.field_type === FieldType.EMAIL
              ? 'email'
              : field.field_type === FieldType.URL
                ? 'url'
                : 'text'
          }
          value={typeof value === 'string' ? value : value == null ? '' : String(value)}
          onChange={(e) => onChange(e.target.value)}
          placeholder={safePlaceholder}
          disabled={disabled}
          className={cn(inputClass, className)}
        />
      )

    case FieldType.NUMBER:
      return (
        <input
          type="number"
          value={value == null || value === '' ? '' : String(value)}
          onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
          step={numberStep}
          placeholder={safePlaceholder}
          disabled={disabled}
          className={cn(inputClass, className)}
        />
      )

    case FieldType.DATE:
      return (
        <DateInput
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value || null)}
          placeholder={safePlaceholder}
          disabled={disabled}
          className={cn('h-9', className)}
        />
      )

    case FieldType.TIME: {
      const granularity = (field.type_config?.time_granularity as string) ?? 'minute'
      return (
        <TimeInput
          step={granularity === 'second' ? 1 : 60}
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value || null)}
          placeholder={safePlaceholder}
          disabled={disabled}
          className={cn('h-9', className)}
        />
      )
    }

    case FieldType.DATETIME:
      return (
        <DateTimeInput
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value || null)}
          placeholder={safePlaceholder}
          disabled={disabled}
          className={cn('h-9', className)}
        />
      )

    case FieldType.SINGLE_SELECT:
      return (
        <OptionComboBox
          options={field.options ?? []}
          multi={shape === 'multi'}
          value={value}
          onChange={onChange}
          placeholder={safePlaceholder}
          disabled={disabled}
          className={className}
        />
      )

    case FieldType.SINGLE_SELECT_TREE:
      return (
        <TreeSelectEditor
          value={value}
          onChange={onChange}
          treeNodes={field.tree_nodes ?? []}
          multi={shape === 'multi'}
          leafOnly={(field.type_config?.leaf_only as boolean) ?? false}
          placeholder={safePlaceholder}
          disabled={disabled ?? false}
          className={className}
        />
      )

    case FieldType.USER_SELECT:
      return (
        <UserSelect
          value={
            shape === 'multi'
              ? (Array.isArray(value) ? value.map(toNumericUserId).filter((v): v is number => v != null) : [])
              : toNumericUserId(value)
          }
          onChange={onChange}
          multi={shape === 'multi'}
          placeholder={safePlaceholder || 'Search users...'}
          disabled={disabled}
          className={className}
        />
      )

    case FieldType.ORGANIZATION_SELECT:
      return (
        <OrganizationSelectEditor
          value={
            shape === 'multi'
              ? (Array.isArray(value) ? value.map(toNumericUserId).filter((v): v is number => v != null) : [])
              : toNumericUserId(value)
          }
          onChange={onChange}
          multi={shape === 'multi'}
          typeConfig={(field.type_config ?? {}) as Record<string, unknown>}
          placeholder={safePlaceholder || 'Search organizations...'}
          disabled={disabled ?? false}
          className={className}
        />
      )

    case FieldType.EMPLOYEE_SELECT:
      return (
        <EmployeeSelect
          value={
            shape === 'multi'
              ? (Array.isArray(value) ? value.map(toNumericUserId).filter((v): v is number => v != null) : [])
              : toNumericUserId(value)
          }
          onChange={onChange}
          multi={shape === 'multi'}
          placeholder={safePlaceholder || 'Search employees...'}
          disabled={disabled}
          className={className}
        />
      )

    case FieldType.GROUP_SELECT:
      return (
        <EmployeeGroupSelect
          value={
            shape === 'multi'
              ? (Array.isArray(value) ? value.map(toNumericUserId).filter((v): v is number => v != null) : [])
              : toNumericUserId(value)
          }
          onChange={onChange}
          multi={shape === 'multi'}
          placeholder={safePlaceholder || 'Search groups...'}
          disabled={disabled}
          className={className}
        />
      )

    // MULTI_SELECT / MULTI_SELECT_TREE / FILE: current operator whitelist
    // only offers is_empty / is_not_empty, so we never reach this branch
    // with a non-empty shape. Fall through to text input as a safe default
    // if the whitelist is ever extended without an editor update.
    default:
      return (
        <input
          type="text"
          value={typeof value === 'string' ? value : value == null ? '' : String(value)}
          onChange={(e) => onChange(e.target.value)}
          placeholder={safePlaceholder}
          disabled={disabled}
          className={cn(inputClass, className)}
        />
      )
  }
}
