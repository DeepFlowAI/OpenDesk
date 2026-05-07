import {
  coalescePillOptions,
  type FieldSelectOption,
} from '@/app/components/features/field-system/field-select-pill-editors'
import type { UnifiedField } from '@/models/field-definition'

/** Resolve pill options from DB options and/or `type_config.options` (system fields). */
export function pillOptionsFromUnifiedField(
  field: UnifiedField | null | undefined,
): FieldSelectOption[] {
  if (!field) return []
  return coalescePillOptions(field.options ?? [], field.type_config)
}

export function labelForSelectValue(
  field: UnifiedField | null | undefined,
  value: string,
): string {
  if (value == null || value === '') return ''
  const opts = pillOptionsFromUnifiedField(field)
  return opts.find((o) => o.value === value)?.label ?? value
}

export function colorForSelectValue(
  field: UnifiedField | null | undefined,
  value: string,
): string | null {
  if (value == null || value === '') return null
  const opts = pillOptionsFromUnifiedField(field)
  return opts.find((o) => o.value === value)?.color ?? null
}
