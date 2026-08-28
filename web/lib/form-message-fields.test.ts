import { describe, expect, it } from 'vitest'

import type { UnifiedField } from '@/models/field-definition'
import {
  configuredFormFieldUid,
  formFieldUid,
  isPublicFormField,
  toConfiguredFormField,
  validateFormMessageConfig,
} from '@/lib/form-message-fields'

const field = (overrides: Partial<UnifiedField>): UnifiedField => ({
  key: null,
  id: 1,
  domain: 'shared_pool',
  source: 'custom',
  name: 'Contact email',
  description: null,
  help_text: null,
  field_type: 'email',
  type_config: {},
  applicable_modules: ['ticket'],
  slot_column: 'str_1',
  show_in_workspace: true,
  sort_order: 0,
  status: 'active',
  options: [],
  tree_nodes: [],
  created_at: null,
  updated_at: null,
  ...overrides,
})

describe('form message fields', () => {
  it('uses ids for custom fields even when the unified response includes a key', () => {
    const customField = field({ id: 24, key: 'contact_email' })
    const systemField = field({ source: 'system', id: null, key: 'title' })

    expect(formFieldUid(customField)).toBe('id:24')
    expect(configuredFormFieldUid(toConfiguredFormField(customField))).toBe('id:24')
    expect(formFieldUid(systemField)).toBe('key:title')
    expect(configuredFormFieldUid(toConfiguredFormField(systemField))).toBe('key:title')
  })

  it('allows safe ticket fields and rejects internal selectors', () => {
    expect(isPublicFormField(field({}))).toBe(true)
    expect(isPublicFormField(field({ field_type: 'employee_select' }))).toBe(false)
    expect(isPublicFormField(field({ source: 'system', key: 'title', id: null }))).toBe(true)
    expect(isPublicFormField(field({ source: 'system', key: 'status', id: null }))).toBe(false)
  })

  it('requires at least one required field', () => {
    const base = {
      title: 'Leave your information',
      description: '',
      submit_label: 'Submit',
      success_title: 'Submitted',
      success_description: 'We received your information.',
      show_ticket_number: true,
      fields: [{ field_key: 'title', field_id: null, required: false }],
    }
    expect(validateFormMessageConfig(base)).toBe('fields_required')
    expect(validateFormMessageConfig({ ...base, fields: [{ ...base.fields[0], required: true }] })).toBeNull()
  })
})
