import type { ChannelFormFieldConfig, ChannelFormMessageConfig } from '@/models/channel'
import type { UnifiedField } from '@/models/field-definition'

const PUBLIC_SYSTEM_FIELD_KEYS = new Set(['title', 'description', 'priority'])
const PUBLIC_FIELD_TYPES = new Set([
  'single_line_text',
  'multi_line_text',
  'number',
  'date',
  'time',
  'datetime',
  'single_select',
  'multi_select',
  'single_select_tree',
  'multi_select_tree',
  'email',
  'phone',
  'url',
  'file',
  'rich_text',
])

export function formFieldUid(field: Pick<UnifiedField, 'source' | 'key' | 'id'>): string {
  return field.source === 'custom' ? `id:${field.id}` : `key:${field.key}`
}

export function configuredFormFieldUid(field: ChannelFormFieldConfig): string {
  return field.field_key ? `key:${field.field_key}` : `id:${field.field_id}`
}

export function isPublicFormField(field: UnifiedField): boolean {
  if (field.status !== 'active' || !PUBLIC_FIELD_TYPES.has(field.field_type)) return false
  if (field.source === 'system') return field.key !== null && PUBLIC_SYSTEM_FIELD_KEYS.has(field.key)
  if (field.source !== 'custom') return false
  if (field.field_type === 'single_select_tree' || field.field_type === 'multi_select_tree') {
    const dataSource = field.type_config.data_source
    if (dataSource !== undefined && dataSource !== 'static') return false
  }
  return true
}

export function toConfiguredFormField(field: UnifiedField): ChannelFormFieldConfig {
  return {
    field_key: field.source === 'system' ? field.key : null,
    field_id: field.source === 'custom' ? field.id : null,
    required: false,
  }
}

export function validateFormMessageConfig(config: ChannelFormMessageConfig): string | null {
  if (!config.title.trim() || config.title.trim().length > 64) return 'title'
  if (config.description.length > 1000) return 'description'
  if (!config.submit_label.trim() || config.submit_label.trim().length > 16) return 'submit_label'
  if (!config.success_title.trim() || config.success_title.trim().length > 64) return 'success_title'
  if (!config.success_description.trim() || config.success_description.trim().length > 1000) {
    return 'success_description'
  }
  if (config.fields.length === 0) return 'fields_empty'
  if (!config.fields.some((field) => field.required)) return 'fields_required'
  const refs = config.fields.map(configuredFormFieldUid)
  if (new Set(refs).size !== refs.length) return 'fields_duplicate'
  return null
}
