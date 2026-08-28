import { describe, expect, it } from 'vitest'

import { formatTaskFieldDescription } from '@/app/components/features/engagement/auto-outbound-task-form'
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
