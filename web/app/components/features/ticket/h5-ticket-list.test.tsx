import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { H5TicketSearchForm } from './h5-ticket-list'

function searchFormProps(overrides: Partial<Parameters<typeof H5TicketSearchForm>[0]> = {}) {
  return {
    isZh: true,
    value: '',
    filterCount: 0,
    onChange: vi.fn(),
    onSubmit: vi.fn(),
    onClear: vi.fn(),
    onFilter: vi.fn(),
    ...overrides,
  }
}

describe('H5TicketSearchForm', () => {
  it('renders an explicit localized search submit button', () => {
    const html = renderToStaticMarkup(createElement(H5TicketSearchForm, searchFormProps()))

    expect(html).toContain('type="submit"')
    expect(html).toContain('aria-label="搜索工单"')
    expect(html).toContain('enterKeyHint="search"')
  })

  it('submits from the explicit search button', async () => {
    const onSubmit = vi.fn()
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    await act(async () => {
      root.render(createElement(H5TicketSearchForm, searchFormProps({ onSubmit })))
    })

    await act(async () => {
      container.querySelector<HTMLButtonElement>('button[type="submit"]')?.click()
    })

    expect(onSubmit).toHaveBeenCalledOnce()

    await act(async () => root.unmount())
    container.remove()
  })

  it('gives the clear button a localized accessible name', () => {
    const html = renderToStaticMarkup(createElement(H5TicketSearchForm, searchFormProps({ value: 'query' })))

    expect(html).toContain('aria-label="清除搜索"')
  })
})
