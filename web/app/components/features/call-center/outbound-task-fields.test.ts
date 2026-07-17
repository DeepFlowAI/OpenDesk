import { describe, expect, it } from 'vitest'

import type { OutboundTaskField } from '@/models/outbound-task'
import { FieldType } from '@/types/field-enums'

import {
  activeOutboundTaskFields,
  isEmptyOutboundFieldValue,
  outboundFieldTreeNodes,
  updateOutboundTargetDraft,
} from './outbound-task-fields'

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

describe('outbound task field helpers', () => {
  it('returns enabled template fields in configured order', () => {
    const fields = activeOutboundTaskFields([
      field({ key: 'later', sort_order: 2 }),
      field({ key: 'disabled', enabled: false, sort_order: 0 }),
      field({ key: 'first', sort_order: 1 }),
    ])

    expect(fields.map((item) => item.key)).toEqual(['first', 'later'])
  })

  it('recognizes empty required values without treating zero as empty', () => {
    expect(isEmptyOutboundFieldValue('  ')).toBe(true)
    expect(isEmptyOutboundFieldValue([])).toBe(true)
    expect(isEmptyOutboundFieldValue(null)).toBe(true)
    expect(isEmptyOutboundFieldValue(0)).toBe(false)
    expect(isEmptyOutboundFieldValue(['selected'])).toBe(false)
  })

  it('flattens template tree options for the shared field components', () => {
    const nodes = outboundFieldTreeNodes(field({
      field_type: FieldType.SINGLE_SELECT_TREE,
      type_config: {
        tree_nodes: [{
          label: '华北',
          value: 'north',
          children: [{ label: '北京', value: 'beijing', children: [] }],
        }],
      },
    }))

    expect(nodes.map(({ label, value, parent_id }) => ({ label, value, parent_id }))).toEqual([
      { label: '华北', value: 'north', parent_id: null },
      { label: '北京', value: 'beijing', parent_id: 1 },
    ])
  })

  it('keeps unsaved field drafts isolated by outbound target', () => {
    let drafts = updateOutboundTargetDraft({}, 10, { result: 'old-a' }, 'result', 'draft-a')
    drafts = updateOutboundTargetDraft(drafts, 20, { result: 'old-b' }, 'result', 'draft-b')
    drafts = updateOutboundTargetDraft(drafts, 10, { result: 'old-a' }, 'notes', 'note-a')

    expect(drafts[10]).toEqual({ result: 'draft-a', notes: 'note-a' })
    expect(drafts[20]).toEqual({ result: 'draft-b' })
  })
})
