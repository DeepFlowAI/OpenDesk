import { describe, expect, it } from 'vitest'

import {
  findDuplicateFieldNames,
  MAX_CALL_VARIABLES,
  normalizeFieldName,
  planFieldVariables,
} from '@/lib/outbound-field-variables'
import type { OutboundTaskField } from '@/models/outbound-task'
import { FieldType } from '@/types/field-enums'

function field(key: string, name: string, overrides: Partial<OutboundTaskField> = {}): OutboundTaskField {
  return {
    key,
    name,
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

describe('normalizeFieldName', () => {
  it('ignores case, spaces and underscores', () => {
    expect(normalizeFieldName(' Customer_Name ')).toBe('customername')
    expect(normalizeFieldName('备 注')).toBe('备注')
  })
})

describe('findDuplicateFieldNames', () => {
  it('flags later fields that collide with an earlier one', () => {
    const result = findDuplicateFieldNames([
      field('field_1', 'customer_name'),
      field('field_2', 'CustomerName'),
      field('field_3', '备注'),
      field('field_4', '备 注', { enabled: false }),
    ])
    expect(result.get('field_2')).toBe('customer_name')
    expect(result.get('field_4')).toBe('备注')
    expect(result.has('field_1')).toBe(false)
    expect(result.has('field_3')).toBe(false)
  })

  it('skips blank names', () => {
    expect(findDuplicateFieldNames([field('field_1', ''), field('field_2', ' ')]).size).toBe(0)
  })
})

describe('planFieldVariables', () => {
  it.each([
    ['customer_name', FieldType.SINGLE_LINE_TEXT, null],
    ['备注', FieldType.SINGLE_LINE_TEXT, 'invalid_name'],
    ['CustomerName', FieldType.SINGLE_LINE_TEXT, 'invalid_name'],
    ['customer name', FieldType.SINGLE_LINE_TEXT, 'invalid_name'],
    ['a'.repeat(33), FieldType.SINGLE_LINE_TEXT, 'too_long'],
    ['a'.repeat(32), FieldType.SINGLE_LINE_TEXT, null],
    ['search_results', FieldType.SINGLE_LINE_TEXT, 'reserved'],
    ['phone_number', FieldType.SINGLE_LINE_TEXT, 'phone_column'],
    ['phonenumber', FieldType.SINGLE_LINE_TEXT, 'phone_column'],
    ['attachment', FieldType.FILE, 'unsupported_type'],
    ['intro', FieldType.RICH_TEXT, 'unsupported_type'],
  ] as const)('classifies %s', (name, fieldType, reason) => {
    const [plan] = planFieldVariables([field('field_1', name, { field_type: fieldType })])
    expect(plan.skipReason).toBe(reason)
  })

  it('omits disabled fields and keeps the earliest of a legacy duplicate', () => {
    const plans = planFieldVariables([
      field('field_1', 'customer_name', { sort_order: 2 }),
      field('field_2', 'customername', { sort_order: 1 }),
      field('field_3', 'note', { enabled: false, sort_order: 0 }),
    ])
    expect(plans.map((plan) => [plan.key, plan.skipReason])).toEqual([
      ['field_2', null],
      ['field_1', 'duplicate'],
    ])
  })

  it('passes at most 20 eligible fields', () => {
    const fields = Array.from({ length: MAX_CALL_VARIABLES + 2 }, (_, i) =>
      field(`field_${i}`, `var_${i}`, { sort_order: i }),
    )
    const plans = planFieldVariables(fields)
    expect(plans.filter((plan) => plan.skipReason === null)).toHaveLength(MAX_CALL_VARIABLES)
    expect(plans.slice(-2).map((plan) => plan.skipReason)).toEqual(['over_limit', 'over_limit'])
  })
})
