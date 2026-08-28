import type { PublicFormMessageField } from '@/models/form-message'

export function publicFormFieldUid(field: PublicFormMessageField): string {
  return field.field_key ? `key:${field.field_key}` : `id:${field.field_id}`
}

export function isFormValueEmpty(value: unknown, fieldType: string): boolean {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') {
    const text = fieldType === 'rich_text' ? value.replace(/<[^>]*>/g, '').replace(/&nbsp;/g, ' ') : value
    return text.trim().length === 0
  }
  if (Array.isArray(value)) return value.length === 0
  return false
}

export function validatePublicFormValues(
  fields: PublicFormMessageField[],
  values: Record<string, unknown>,
): Record<string, 'required' | 'format'> {
  const errors: Record<string, 'required' | 'format'> = {}
  for (const field of fields) {
    const uid = publicFormFieldUid(field)
    const value = values[uid]
    const fieldType = field.definition.field_type
    if (field.required && isFormValueEmpty(value, fieldType)) {
      errors[uid] = 'required'
      continue
    }
    if (isFormValueEmpty(value, fieldType)) continue
    if (fieldType === 'email' && (typeof value !== 'string' || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value))) {
      errors[uid] = 'format'
    }
    if (fieldType === 'url' && (typeof value !== 'string' || !/^https?:\/\//i.test(value))) {
      errors[uid] = 'format'
    }
  }
  return errors
}
