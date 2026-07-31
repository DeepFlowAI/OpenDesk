import { beforeEach, describe, expect, it, vi } from 'vitest'

const trackApp = vi.fn()
const flushApp = vi.fn()

vi.mock('@/service/telemetry', () => ({
  telemetry: {
    trackApp: (...args: unknown[]) => trackApp(...args),
    flushApp: (...args: unknown[]) => flushApp(...args),
  },
}))

vi.hoisted(() => {
  const values = new Map<string, string>()
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value)
      },
      removeItem: (key: string) => {
        values.delete(key)
      },
      clear: () => {
        values.clear()
      },
    },
  })
})

import { useAuthStore } from '@/context/auth-store'
import type { UserInfo } from '@/models/auth'
import { logAuthEvent } from '@/utils/auth-log'

function user(partial: Partial<UserInfo> = {}): UserInfo {
  return {
    id: 42,
    username: 'agent',
    name: 'Agent',
    display_name: null,
    avatar: null,
    roles: [],
    tenant_id: 7,
    role_ids: [],
    permissions: [],
    data_scopes: {},
    is_super_admin: false,
    group_ids: [],
    preferences: {},
    ...partial,
  }
}

beforeEach(() => {
  trackApp.mockClear()
  flushApp.mockClear()
  localStorage.clear()
  useAuthStore.setState({ user: null, token: null })
})

describe('logAuthEvent', () => {
  it('includes user_id and tenant_id from the in-memory auth store', async () => {
    useAuthStore.setState({ user: user({ id: 42, tenant_id: 7 }), token: 't' })

    await logAuthEvent('session_cleared', { trigger: 'token_expired' })

    expect(trackApp).toHaveBeenCalledTimes(1)
    const [, input] = trackApp.mock.calls[0] as [string, { props: Record<string, unknown> }]
    expect(input.props.user_id).toBe(42)
    expect(input.props.tenant_id).toBe(7)
    expect(input.props.trigger).toBe('token_expired')
    expect(typeof input.props.tab_id).toBe('string')
    expect(input.props.visibility).toBeDefined()
  })

  it('falls back to persisted app-auth when memory has no user', async () => {
    localStorage.setItem(
      'app-auth',
      JSON.stringify({ state: { user: { id: 99, tenant_id: 3 } } }),
    )

    await logAuthEvent('token_refresh_failed', { status: 404 })

    expect(trackApp).toHaveBeenCalledTimes(1)
    const [, input] = trackApp.mock.calls[0] as [string, { props: Record<string, unknown> }]
    expect(input.props.user_id).toBe(99)
    expect(input.props.tenant_id).toBe(3)
  })
})
