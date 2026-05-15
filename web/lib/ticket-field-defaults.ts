import type { FdFormLayoutField, FdFormLayoutTab } from '@/models/form-layout'
import type { UnifiedField } from '@/models/field-definition'
import type { CustomFieldValue } from '@/types/custom-field-value'
import { FieldType } from '@/types/field-enums'

/**
 * Layout field key — keep in sync with TicketCreateForm.getFieldKey.
 */
export function layoutFieldKey(field: FdFormLayoutField): string {
  if (field.field_key) return field.field_key
  if (field.field_definition_id) return String(field.field_definition_id)
  return `field_${field.id}`
}

/**
 * Map type_config.default_value from a unified field definition to the shape
 * TicketCreateForm / FieldInput expect in form state.
 */
export function typeConfigDefaultToFormValue(def: UnifiedField): unknown | undefined {
  const raw = def.type_config?.default_value
  if (raw === null || raw === undefined) return undefined
  if (raw === '') return undefined

  const ft = def.field_type

  switch (ft) {
    case FieldType.MULTI_SELECT:
    case FieldType.MULTI_SELECT_TREE: {
      if (Array.isArray(raw)) {
        const parts = raw.map((x) => String(x).trim()).filter(Boolean)
        return parts.length ? parts : undefined
      }
      if (typeof raw === 'string' && raw.trim()) {
        const parts = raw.split(',').map((s) => s.trim()).filter(Boolean)
        return parts.length ? parts : undefined
      }
      return undefined
    }
    case FieldType.NUMBER: {
      if (typeof raw === 'number' && !Number.isNaN(raw)) return raw
      if (typeof raw === 'string' && raw.trim() !== '') {
        const n = Number(raw)
        return Number.isFinite(n) ? n : undefined
      }
      return undefined
    }
    case FieldType.SINGLE_SELECT:
    case FieldType.SINGLE_SELECT_TREE:
    case FieldType.SINGLE_LINE_TEXT:
    case FieldType.MULTI_LINE_TEXT:
    case FieldType.EMAIL:
    case FieldType.PHONE:
    case FieldType.URL:
    case FieldType.DATE:
    case FieldType.TIME:
    case FieldType.DATETIME:
      return typeof raw === 'string' ? raw : String(raw)
    default:
      return raw
  }
}

function toCustomFieldDefault(v: unknown): CustomFieldValue | undefined {
  if (v === undefined) return undefined
  if (v === null) return null
  if (typeof v === 'string' || typeof v === 'number' || typeof v === 'boolean') return v
  if (Array.isArray(v)) return v as CustomFieldValue
  return undefined
}

/**
 * Defaults for user/org create modals — keyed by semantic field key, with id fallback.
 */
export function defaultCfValuesFromFieldDefinitions(fields: UnifiedField[]): Record<string, CustomFieldValue> {
  const out: Record<string, CustomFieldValue> = {}
  for (const f of fields) {
    if (f.id == null) continue
    const key = f.key ?? String(f.id)
    const raw = typeConfigDefaultToFormValue(f)
    const v = toCustomFieldDefault(raw)
    if (v === undefined) continue
    out[key] = v
  }
  return out
}

/**
 * Only DB-backed custom definitions carry editable type_config defaults.
 * System unified fields use id === null.
 */
function isCustomDefinitionField(def: UnifiedField): boolean {
  return def.id != null
}

/**
 * Collect default form values from all fields on the new_ticket layout.
 */
export function collectLayoutFieldDefaults(
  layout: { tabs?: FdFormLayoutTab[] } | null | undefined,
  fieldDefMap: Map<string, UnifiedField>,
): Record<string, unknown> {
  if (!layout?.tabs?.length) return {}
  const out: Record<string, unknown> = {}

  for (const tab of layout.tabs) {
    for (const section of tab.sections ?? []) {
      for (const field of section.fields ?? []) {
        const key = layoutFieldKey(field)
        const def = field.field_key
          ? fieldDefMap.get(field.field_key)
          : field.field_definition_id != null
            ? fieldDefMap.get(String(field.field_definition_id))
            : undefined
        if (!def || !isCustomDefinitionField(def)) continue
        const v = typeConfigDefaultToFormValue(def)
        if (v !== undefined) out[key] = v
      }
    }
  }
  return out
}

function isFormValueEmpty(value: unknown): boolean {
  return value === undefined || value === null || value === ''
}

/**
 * Merge type_config defaults into form state for keys that are still empty
 * and were not explicitly set via initialValues.
 */
export function mergeCustomFieldDefaultsIntoForm(
  prev: Record<string, unknown>,
  layout: { tabs?: FdFormLayoutTab[] } | null | undefined,
  fieldDefMap: Map<string, UnifiedField>,
  initialValues: Record<string, unknown> | undefined,
): Record<string, unknown> {
  const defaults = collectLayoutFieldDefaults(layout, fieldDefMap)
  let changed = false
  const next = { ...prev }

  for (const [k, v] of Object.entries(defaults)) {
    if (initialValues && Object.prototype.hasOwnProperty.call(initialValues, k)) continue
    if (!isFormValueEmpty(next[k])) continue
    if (v === undefined) continue
    next[k] = v
    changed = true
  }

  return changed ? next : prev
}
