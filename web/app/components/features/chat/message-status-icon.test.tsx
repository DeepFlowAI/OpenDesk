import { act, createElement } from 'react'
import { createRoot } from 'react-dom/client'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import { MessageStatusIcon, resolveVisibleMessageStatus } from './message-status-icon'

describe('resolveVisibleMessageStatus', () => {
  it('keeps sending visible when read-status display is disabled', () => {
    expect(resolveVisibleMessageStatus('sending', { enabled: false })).toBe('sending')
  })

  it('maps Web SDK delivered status to unread', () => {
    expect(resolveVisibleMessageStatus('delivered', {
      enabled: true,
      deliveredAsUnread: true,
    })).toBe('unread')
  })

  it('keeps offline-message feedback visible when configured', () => {
    expect(resolveVisibleMessageStatus('offline', {
      enabled: false,
      alwaysShowOffline: true,
    })).toBe('offline')
  })

  it('hides failed and unknown states', () => {
    expect(resolveVisibleMessageStatus('failed', { enabled: true })).toBeNull()
    expect(resolveVisibleMessageStatus(undefined, { enabled: true })).toBeNull()
  })
})

describe('MessageStatusIcon', () => {
  it('renders a fixed trigger with an accessible localized name', () => {
    const html = renderToStaticMarkup(createElement(MessageStatusIcon, {
      status: 'unread',
      locale: 'zh',
    }))

    expect(html).toContain('aria-label="未读"')
    expect(html).toContain('h-5 w-5')
    expect(html).toContain('h-4 w-4 text-[#93C5FD]')
    expect(html).not.toContain('title=')
  })

  it.each(['sending', 'offline', 'unread', 'read'] as const)('uses medium blue for %s status', (status) => {
    const html = renderToStaticMarkup(createElement(MessageStatusIcon, {
      status,
      locale: 'zh',
    }))

    expect(html).toContain('text-[#93C5FD]')
    expect(html).not.toContain('text-[#DBEAFE]')
    expect(html).not.toContain('text-info')
    expect(html).not.toContain('text-warning')
    expect(html).not.toContain('text-muted-foreground')
  })

  it('uses neutral gray only when the visitor chat requests it', () => {
    const html = renderToStaticMarkup(createElement(MessageStatusIcon, {
      status: 'read',
      locale: 'zh',
      tone: 'gray',
    }))

    expect(html).toContain('text-[#A3A3A3]')
    expect(html).not.toContain('text-[#93C5FD]')
  })

  it('opens the custom tooltip immediately on keyboard focus', async () => {
    const container = document.createElement('div')
    document.body.appendChild(container)
    const root = createRoot(container)

    await act(async () => {
      root.render(createElement(MessageStatusIcon, { status: 'read', locale: 'en' }))
    })

    await act(async () => {
      container.querySelector<HTMLElement>('[role="img"]')?.focus()
    })

    expect(document.body.querySelector('[role="tooltip"]')?.textContent).toBe('Read')

    await act(async () => root.unmount())
    container.remove()
  })
})
