import { describe, expect, it } from 'vitest'

import type { OutboundTaskField } from '@/models/outbound-task'
import { FieldType } from '@/types/field-enums'

import {
  autoOutboundTargetDetailFields,
  autoOutboundTargetListFields,
} from './auto-outbound-target-fields'

function field(overrides: Partial<OutboundTaskField>): OutboundTaskField {
  return {
    key: 'field_1',
    name: '字段',
    field_type: FieldType.SINGLE_LINE_TEXT,
    required: false,
    agent_editable: false,
    show_in_list: true,
    enabled: true,
    type_config: {},
    sort_order: 0,
    ...overrides,
  }
}

describe('autoOutboundTargetListFields', () => {
  it('keeps every enabled list field in configured order', () => {
    const fields = autoOutboundTargetListFields([
      field({ key: 'third', sort_order: 3 }),
      field({ key: 'hidden', show_in_list: false, sort_order: 0 }),
      field({ key: 'first', sort_order: 1 }),
      field({ key: 'disabled', enabled: false, sort_order: 0 }),
      field({ key: 'second', sort_order: 2 }),
    ])

    expect(fields.map((item) => item.key)).toEqual(['first', 'second', 'third'])
  })
})

describe('autoOutboundTargetDetailFields', () => {
  it('keeps all enabled fields in configured order', () => {
    const fields = autoOutboundTargetDetailFields([
      field({ key: 'third', show_in_list: false, sort_order: 3 }),
      field({ key: 'disabled', enabled: false, sort_order: 0 }),
      field({ key: 'first', sort_order: 1 }),
      field({ key: 'second', show_in_list: false, sort_order: 2 }),
    ])

    expect(fields.map((item) => item.key)).toEqual(['first', 'second', 'third'])
  })
})
