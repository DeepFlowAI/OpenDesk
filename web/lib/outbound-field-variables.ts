import type { OutboundTaskField } from '@/models/outbound-task'

// Limits VoiceSpeed enforces on call variables; keep in sync with the server.
export const MAX_CALL_VARIABLES = 20
const MAX_VARIABLE_NAME_LENGTH = 32
const RESERVED_VARIABLE_NAMES = new Set(['search_results'])
const UNSUPPORTED_FIELD_TYPES = new Set<string>(['file', 'rich_text'])
const VARIABLE_NAME_PATTERN = /^[a-z][a-z0-9_]*$/
// Headers spreadsheet import treats as the phone-number column.
const PHONE_HEADER_ALIASES = ['phone_number', 'phone', 'mobile', 'tel', '呼叫号码', '号码', '手机号', '手机号码', '联系电话']

export type FieldVariableSkipReason =
  | 'unsupported_type'
  | 'invalid_name'
  | 'too_long'
  | 'reserved'
  | 'phone_column'
  | 'duplicate'
  | 'over_limit'

export type FieldVariablePlan = {
  key: string
  name: string
  skipReason: FieldVariableSkipReason | null
}

/** Compare field names the same way spreadsheet import matches headers. */
export function normalizeFieldName(name: string): string {
  return name.trim().toLowerCase().replace(/[ _]/g, '')
}

const PHONE_ALIASES = new Set(PHONE_HEADER_ALIASES.map(normalizeFieldName))

function nameSkipReason(name: string): FieldVariableSkipReason | null {
  if (!VARIABLE_NAME_PATTERN.test(name)) return 'invalid_name'
  if (name.length > MAX_VARIABLE_NAME_LENGTH) return 'too_long'
  if (RESERVED_VARIABLE_NAMES.has(name)) return 'reserved'
  if (PHONE_ALIASES.has(normalizeFieldName(name))) return 'phone_column'
  return null
}

/**
 * Decide which enabled fields a voice bot call passes as `{{name}}` variables,
 * in sort order. Mirrors the server rules applied when the call connects.
 */
export function planFieldVariables(fields: OutboundTaskField[]): FieldVariablePlan[] {
  const enabled = fields
    .map((field, index) => ({ field, index }))
    .filter(({ field }) => field.enabled)
    .sort((a, b) => (a.field.sort_order ?? 0) - (b.field.sort_order ?? 0) || a.index - b.index)

  const seen = new Set<string>()
  let passed = 0
  return enabled.map(({ field }) => {
    const name = field.name.trim()
    const normalized = normalizeFieldName(name)
    let reason = UNSUPPORTED_FIELD_TYPES.has(field.field_type) ? 'unsupported_type' : nameSkipReason(name)
    if (reason === null && seen.has(normalized)) reason = 'duplicate'
    if (reason === null && passed >= MAX_CALL_VARIABLES) reason = 'over_limit'
    seen.add(normalized)
    if (reason === null) passed += 1
    return { key: field.key, name, skipReason: reason }
  })
}

/**
 * Map each duplicated field key to the name of the earlier field it collides
 * with. Disabled fields count; blank names are left to the required check.
 */
export function findDuplicateFieldNames(fields: OutboundTaskField[]): Map<string, string> {
  const seen = new Map<string, string>()
  const duplicates = new Map<string, string>()
  for (const field of fields) {
    const normalized = normalizeFieldName(field.name)
    if (!normalized) continue
    const earlier = seen.get(normalized)
    if (earlier !== undefined) duplicates.set(field.key, earlier)
    else seen.set(normalized, field.name.trim())
  }
  return duplicates
}
