import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/app/components/features/call-center/outbound-number-select', () => ({
  OutboundNumberSelect: () => createElement('div'),
}))

vi.mock('@/app/components/features/call-center/dial-pad', () => ({
  DialPad: () => null,
}))

vi.mock('@/hooks/use-workspace-call-outbound-preference', () => ({
  useWorkspaceCallOutboundPreference: () => ({
    preferredId: undefined,
    savePreferredId: () => undefined,
  }),
}))

import { DialBar } from './dial-bar'

describe('DialBar', () => {
  it('shows an externally provided draft number after mount', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    await act(async () => {
      root.render(createElement(DialBar, { value: '' }))
    })
    expect(container.querySelector('input')?.value).toBe('')

    await act(async () => {
      root.render(createElement(DialBar, { value: '18601123206' }))
    })
    expect(container.querySelector('input')?.value).toBe('18601123206')

    await act(async () => root.unmount())
    container.remove()
  })
})
