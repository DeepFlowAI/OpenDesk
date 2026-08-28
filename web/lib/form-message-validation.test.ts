import { describe, expect, it } from 'vitest'

import type { PublicFormMessageField } from '@/models/form-message'
import { validatePublicFormValues } from '@/lib/form-message-validation'

const field = (fieldType: PublicFormMessageField['definition']['field_type']): PublicFormMessageField => ({
  field_key: null,
  field_id: 7,
  required: true,
  definition: {
    key: null,
    id: 7,
    domain: 'shared_pool',
    source: 'custom',
    name: 'Email',
    description: null,
    help_text: null,
    field_type: fieldType,
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
  },
})

describe('public form message validation', () => {
  it('requires configured required fields', () => {
    expect(validatePublicFormValues([field('single_line_text')], {})).toEqual({ 'id:7': 'required' })
  })

  it('validates email format', () => {
    expect(validatePublicFormValues([field('email')], { 'id:7': 'invalid' })).toEqual({ 'id:7': 'format' })
    expect(validatePublicFormValues([field('email')], { 'id:7': 'hello@example.com' })).toEqual({})
  })
})
