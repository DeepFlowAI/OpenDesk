import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import {
  FieldValueEditor,
  resolveDefaultFieldPlaceholder,
} from '@/app/components/features/field-system/field-value-editor'
import { FieldType } from '@/types/field-enums'

describe('field value editor default placeholders', () => {
  it.each([
    FieldType.SINGLE_LINE_TEXT,
    FieldType.MULTI_LINE_TEXT,
    FieldType.NUMBER,
    FieldType.EMAIL,
    FieldType.PHONE,
    FieldType.URL,
    FieldType.RICH_TEXT,
  ])('localizes the input placeholder for %s', (fieldType) => {
    expect(resolveDefaultFieldPlaceholder(fieldType, 'en')).toBe('Please enter')
  })

  it.each([
    FieldType.DATE,
    FieldType.TIME,
    FieldType.DATETIME,
    FieldType.SINGLE_SELECT,
    FieldType.MULTI_SELECT,
    FieldType.SINGLE_SELECT_TREE,
    FieldType.MULTI_SELECT_TREE,
  ])('localizes the selection placeholder for %s', (fieldType) => {
    expect(resolveDefaultFieldPlaceholder(fieldType, 'en')).toBe('Please select')
  })

  it.each([
    [FieldType.USER_SELECT, 'Select user'],
    [FieldType.ORGANIZATION_SELECT, 'Select organization'],
    [FieldType.EMPLOYEE_SELECT, 'Select employee'],
    [FieldType.GROUP_SELECT, 'Select responsible group'],
    [FieldType.FILE, 'Upload file'],
  ] as const)('localizes the specialized placeholder for %s', (fieldType, expected) => {
    expect(resolveDefaultFieldPlaceholder(fieldType, 'en')).toBe(expected)
  })

  it('keeps explicitly configured placeholders unchanged', () => {
    const html = renderToStaticMarkup(
      <FieldValueEditor
        fieldType={FieldType.MULTI_LINE_TEXT}
        value=""
        onChange={() => undefined}
        placeholder="Describe your request"
        locale="en"
      />,
    )

    expect(html).toContain('placeholder="Describe your request"')
    expect(html).not.toContain('placeholder="Please enter"')
  })

  it('preserves the legacy Chinese default when locale is not provided', () => {
    expect(resolveDefaultFieldPlaceholder(FieldType.MULTI_LINE_TEXT)).toBe('请输入')
  })
})
