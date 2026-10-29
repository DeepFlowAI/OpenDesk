import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import {
  CallVariablesPreview,
  formatTaskFieldDescription,
} from '@/app/components/features/engagement/auto-outbound-task-form'
import type { OutboundTaskField } from '@/models/outbound-task'
import { FieldType } from '@/types/field-enums'

describe('formatTaskFieldDescription', () => {
  it('shows the Chinese field type name and editable marker', () => {
    expect(formatTaskFieldDescription(FieldType.SINGLE_SELECT, true, 'zh')).toBe('单选 · 客服可编辑')
  })

  it('shows the English field type name and editable marker', () => {
    expect(formatTaskFieldDescription(FieldType.SINGLE_LINE_TEXT, true, 'en')).toBe(
      'Single Line Text · Agent editable',
    )
  })

  it('omits the editable marker for read-only fields', () => {
    expect(formatTaskFieldDescription(FieldType.MULTI_LINE_TEXT, false, 'zh')).toBe('多行文本')
  })
})

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

describe('CallVariablesPreview', () => {
  it('lists passed fields and skipped fields with reasons', () => {
    const html = renderToStaticMarkup(
      createElement(CallVariablesPreview, {
        locale: 'zh',
        agentChanged: false,
        fields: [
          field('field_1', 'customer_name', { sort_order: 0 }),
          field('field_2', '备注', { sort_order: 1 }),
          field('field_3', 'phone', { sort_order: 2 }),
          field('field_4', 'disabled_note', { sort_order: 3, enabled: false }),
        ],
      }),
    )

    expect(html).toContain('customer_name')
    expect(html).toContain('将作为变量传入')
    expect(html).toContain('名称不是 VoiceSpeed 变量名')
    expect(html).toContain('号码列不传入')
    expect(html).not.toContain('disabled_note')
    expect(html).not.toContain('最多传入 20 个变量')
    expect(html).not.toContain('请确认字段名称')
  })

  it('shows the empty state and agent-change reminder', () => {
    const html = renderToStaticMarkup(
      createElement(CallVariablesPreview, { locale: 'zh', agentChanged: true, fields: [] }),
    )

    expect(html).toContain('当前任务没有业务字段')
    expect(html).toContain('请确认字段名称与当前 Agent 提示词中的 {{变量名}} 一致。')
  })

  it('warns when more than 20 fields qualify', () => {
    const fields = Array.from({ length: 21 }, (_, i) => field(`field_${i}`, `var_${i}`, { sort_order: i }))
    const html = renderToStaticMarkup(
      createElement(CallVariablesPreview, { locale: 'zh', agentChanged: false, fields }),
    )

    expect(html).toContain('最多传入 20 个变量，请把提示词用到的字段在模板中排在前面。')
    expect(html).toContain('超过 20 个变量')
  })
})
