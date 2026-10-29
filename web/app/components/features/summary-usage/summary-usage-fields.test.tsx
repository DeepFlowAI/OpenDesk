import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FieldType } from '@/types/field-enums'
import { SummaryUsageFields, type SummaryUsageConfigField } from './summary-usage-fields'

;(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true

function textField(id: number, name: string): SummaryUsageConfigField {
  return {
    id,
    config_id: 1,
    field_definition_id: id,
    field_key: null,
    sort_order: id,
    is_active: true,
    field_definition: {
      id,
      name,
      field_type: FieldType.SINGLE_LINE_TEXT,
      type_config: {},
      options: [],
    } as unknown as SummaryUsageConfigField['field_definition'],
  }
}

const texts = {
  loading: 'loading',
  loadFailed: 'failed',
  empty: 'empty',
  retry: 'retry',
  fieldRequired: 'required',
  saveFailed: 'save failed',
  editField: 'Edit',
}

describe('SummaryUsageFields', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it('keeps the next field open when the previous field finishes saving', async () => {
    let finishSave: () => void = () => {}
    const onSaveField = vi.fn(() => new Promise<void>((resolve) => { finishSave = resolve }))
    act(() => {
      root.render(
        <SummaryUsageFields
          fields={[textField(1, 'A'), textField(2, 'B')]}
          values={{}}
          texts={texts}
          onSaveField={onSaveField}
        />,
      )
    })

    const editButton = (name: string) =>
      container.querySelector<HTMLButtonElement>(`button[aria-label="Edit ${name}"]`)

    act(() => editButton('A')!.click())
    const inputA = container.querySelector<HTMLInputElement>('[data-summary-field="1"] input')!
    act(() => {
      const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!
      setValue.call(inputA, '222')
      inputA.dispatchEvent(new Event('input', { bubbles: true }))
    })

    // Leaving A saves it; the click that caused the blur opens B.
    act(() => inputA.blur())
    expect(onSaveField).toHaveBeenCalledTimes(1)
    act(() => editButton('B')!.click())
    await act(async () => finishSave())

    const inputB = container.querySelector<HTMLInputElement>('[data-summary-field="2"] input')
    expect(inputB).not.toBeNull()
    expect(inputB!.disabled).toBe(false)
  })
})
