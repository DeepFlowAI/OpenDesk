import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import { H5TicketShell } from './h5-ticket-shell'

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
}))

vi.mock('@/context/auth-store', () => ({
  useAuthStore: () => ({
    user: { username: 'e2e_admin' },
    clearAuth: vi.fn(),
  }),
}))

vi.mock('@/context/locale-store', () => ({
  useLocaleStore: () => ({
    locale: 'zh',
    setLocale: vi.fn(),
  }),
}))

describe('H5TicketShell', () => {
  it('gives the account menu trigger a localized accessible name', () => {
    const html = renderToStaticMarkup(
      <H5TicketShell title="工单">
        <div>content</div>
      </H5TicketShell>,
    )

    expect(html).toContain('aria-label="账号菜单"')
  })
})
