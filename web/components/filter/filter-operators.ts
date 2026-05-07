/**
 * Shared filter operator registry for users / organizations / tickets.
 *
 * The operator whitelist is intentionally aligned with what the backend
 * repositories actually implement (see `server/app/repositories/
 * user_repository.py::_build_condition_clause` and the organization /
 * ticket counterparts). Operators the backend cannot evaluate yet
 * (`between`, `overlaps`, `contains_all`, `is_descendant_of`, ...) are
 * NOT exposed here so the UI never offers a broken choice.
 *
 * When those operators become supported server-side, extend the tables
 * below — consumers (`FilterValueEditor`, drawer, view config tabs)
 * already handle every shape.
 */

import { FieldType } from '@/types/field-enums'

/** Operators that do not take a value input. */
export const NO_VALUE_OPS = new Set<string>(['is_empty', 'is_not_empty'])

/** Operators whose value is an array (multi pick). */
export const MULTI_VALUE_OPS = new Set<string>(['in', 'not_in'])

/** Backend-supported operator whitelist, keyed by field_type. */
export const OPERATORS_BY_TYPE: Record<string, string[]> = {
  [FieldType.SINGLE_LINE_TEXT]: [
    'is_empty', 'is_not_empty', 'eq', 'ne',
    'contains', 'not_contains', 'starts_with', 'ends_with',
  ],
  [FieldType.MULTI_LINE_TEXT]: [
    'is_empty', 'is_not_empty', 'eq', 'ne',
    'contains', 'not_contains', 'starts_with', 'ends_with',
  ],
  [FieldType.EMAIL]: [
    'is_empty', 'is_not_empty', 'eq', 'ne',
    'contains', 'not_contains', 'starts_with', 'ends_with',
  ],
  [FieldType.PHONE]: [
    'is_empty', 'is_not_empty', 'eq', 'ne',
    'contains', 'not_contains', 'starts_with', 'ends_with',
  ],
  [FieldType.URL]: [
    'is_empty', 'is_not_empty', 'eq', 'ne',
    'contains', 'not_contains', 'starts_with', 'ends_with',
  ],
  [FieldType.RICH_TEXT]: ['is_empty', 'is_not_empty', 'contains', 'not_contains'],

  [FieldType.NUMBER]: ['is_empty', 'is_not_empty', 'eq', 'ne', 'gt', 'gte', 'lt', 'lte'],
  [FieldType.DATE]: ['is_empty', 'is_not_empty', 'eq', 'ne', 'gt', 'gte', 'lt', 'lte'],
  [FieldType.TIME]: ['is_empty', 'is_not_empty', 'eq', 'ne', 'gt', 'gte', 'lt', 'lte'],
  [FieldType.DATETIME]: ['is_empty', 'is_not_empty', 'eq', 'ne', 'gt', 'gte', 'lt', 'lte'],

  [FieldType.SINGLE_SELECT]: ['is_empty', 'is_not_empty', 'eq', 'ne', 'in', 'not_in'],
  [FieldType.SINGLE_SELECT_TREE]: ['is_empty', 'is_not_empty', 'eq', 'ne', 'in', 'not_in'],

  // Backend cannot yet evaluate JSON-array containment for these types.
  // Only empty-checks are exposed; extend once repositories implement
  // overlaps / contains_all / is_descendant_of.
  [FieldType.MULTI_SELECT]: ['is_empty', 'is_not_empty'],
  [FieldType.MULTI_SELECT_TREE]: ['is_empty', 'is_not_empty'],

  [FieldType.FILE]: ['is_empty', 'is_not_empty'],
  [FieldType.USER_SELECT]: ['is_empty', 'is_not_empty', 'eq', 'ne', 'in', 'not_in'],
  [FieldType.EMPLOYEE_SELECT]: ['is_empty', 'is_not_empty', 'eq', 'ne', 'in', 'not_in'],
  [FieldType.GROUP_SELECT]: ['is_empty', 'is_not_empty', 'eq', 'ne', 'in', 'not_in'],
}

export type ValueShape = 'none' | 'single' | 'multi'

/** How many / what kind of values a given operator expects. */
export function valueShape(operator: string): ValueShape {
  if (!operator) return 'none'
  if (NO_VALUE_OPS.has(operator)) return 'none'
  if (MULTI_VALUE_OPS.has(operator)) return 'multi'
  return 'single'
}

/** Whether the operator expects an array value. */
export function isMultiValueOp(operator: string): boolean {
  return valueShape(operator) === 'multi'
}

/** Return allowed operators for a field type (empty array when unknown). */
export function operatorsForFieldType(fieldType: string | undefined | null): string[] {
  if (!fieldType) return []
  return OPERATORS_BY_TYPE[fieldType] ?? []
}

/** Validate a condition's value matches the operator's expected shape. */
export function isConditionValueComplete(operator: string, value: unknown): boolean {
  const shape = valueShape(operator)
  if (shape === 'none') return true
  if (shape === 'multi') return Array.isArray(value) && value.length > 0
  if (value == null) return false
  if (Array.isArray(value)) return value.length > 0
  return String(value).trim() !== ''
}
