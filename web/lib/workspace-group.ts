/**
 * Workspace view-group helpers shared by the ticket / user / organization
 * workspaces. Mirrors the server's `EMPTY_GROUP_VALUE` sentinel so the client
 * can ask the API to filter records whose group field is NULL.
 */
import type { Locale } from '@/context/locale-store'
import type { UnifiedField } from '@/models/field-definition'
import { formatDatetimeForDisplay } from '@/lib/datetime-display'

// Must stay in sync with `app/core/constants.py::EMPTY_GROUP_VALUE`.
export const EMPTY_GROUP_VALUE = '__EMPTY__'

const SELECT_LIKE = new Set([
  'single_select',
  'multi_select',
  'single_select_tree',
  'multi_select_tree',
])

type ValueLookup = Map<string, string>

export function buildSelectLookup(
  field: UnifiedField | null | undefined,
): ValueLookup | null {
  if (!field || !SELECT_LIKE.has(field.field_type)) return null
  const map: ValueLookup = new Map()
  for (const o of field.options ?? []) {
    if (o.is_active) map.set(o.value, o.label)
  }
  for (const n of field.tree_nodes ?? []) {
    if (n.is_active) map.set(n.value, n.label)
  }
  const cfgOpts = (field.type_config as { options?: { label: string; value: string }[] } | undefined)
    ?.options
  if (cfgOpts) {
    for (const o of cfgOpts) {
      map.set(o.value, o.label)
    }
  }
  return map.size ? map : null
}

/**
 * Convert a group's raw string value into a human-readable label.
 *  - `null` value     → localized "Unassigned" placeholder
 *  - select-like      → resolved option/tree label, falls back to raw
 *  - datetime         → locale-formatted timestamp
 *  - default          → raw passthrough
 */
export function formatGroupLabel(
  raw: string | null,
  field: { field_type: string } | null,
  selectLookup: ValueLookup | null,
  locale: Locale,
): string {
  if (raw == null) return locale === 'zh' ? '空' : 'Unassigned'
  if (!field) return raw
  if (selectLookup) {
    if (raw.includes(',')) {
      return raw
        .split(',')
        .map((v) => selectLookup.get(v.trim()) ?? v.trim())
        .join(', ')
    }
    return selectLookup.get(raw) ?? raw
  }
  if (field.field_type === 'datetime') return formatDatetimeForDisplay(raw)
  return raw
}
