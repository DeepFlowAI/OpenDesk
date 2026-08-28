import { act, createElement } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { TenantPhoneNumber } from '@/models/tenant-phone-number'

const mocks = vi.hoisted(() => ({
  numbers: [] as TenantPhoneNumber[],
}))

vi.mock('@/service/use-tenant-phone-numbers', () => ({
  useMyOutboundNumbers: () => ({
    data: { items: mocks.numbers, total: mocks.numbers.length },
    isLoading: false,
  }),
}))

import { OutboundNumberSelect } from './outbound-number-select'

function number(id: string, phone: string): TenantPhoneNumber {
  return {
    id,
    phone_number: phone,
    call_types: ['outbound'],
    tags: [],
    outbound_time_slots: [],
    created_at: null,
    updated_at: null,
  }
}

describe('OutboundNumberSelect', () => {
  let container: HTMLDivElement
  let root: Root

  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true
    mocks.numbers = [number('pn-1', '1001'), number('pn-2', '1002')]
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(async () => {
    await act(async () => root.unmount())
    container.remove()
  })

  it('auto-selects the preferred outbound number when it is still available', async () => {
    const onChange = vi.fn()

    await act(async () => {
      root.render(
        createElement(OutboundNumberSelect, {
          value: '',
          preferredId: 'pn-2',
          onChange,
        }),
      )
    })

    expect(onChange).toHaveBeenCalledWith('pn-2', '1002', 'auto')
  })

  it('falls back to the first outbound number when no preference is stored', async () => {
    const onChange = vi.fn()

    await act(async () => {
      root.render(
        createElement(OutboundNumberSelect, {
          value: '',
          onChange,
        }),
      )
    })

    expect(onChange).toHaveBeenCalledWith('pn-1', '1001', 'auto')
  })
})
