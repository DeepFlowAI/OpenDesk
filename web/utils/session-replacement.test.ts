import { beforeEach, describe, expect, it, vi } from 'vitest'

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

import {
  AUTH_STORE_KEY,
  SESSION_EXPIRED_REASON,
  SESSION_REPLACED_REASON,
  buildForcedLoginUrl,
  buildSessionExpiredLoginUrl,
  buildSessionReplacedLoginUrl,
  clearStoredAuth,
  isForcedLoginReason,
  redirectToSessionExpiredLogin,
} from '@/utils/session-replacement'

beforeEach(() => {
  localStorage.clear()
  window.history.replaceState({}, '', '/workspace/chat')
})

describe('session-replacement helpers', () => {
  it('recognizes forced-login reason query values', () => {
    expect(isForcedLoginReason(SESSION_REPLACED_REASON)).toBe(true)
    expect(isForcedLoginReason(SESSION_EXPIRED_REASON)).toBe(true)
    expect(isForcedLoginReason('other')).toBe(false)
    expect(isForcedLoginReason(null)).toBe(false)
  })

  it('builds login urls with reason and redirect', () => {
    expect(buildSessionReplacedLoginUrl()).toBe(
      `/login?reason=${SESSION_REPLACED_REASON}&redirect=${encodeURIComponent('/workspace/chat')}`,
    )
    expect(buildSessionExpiredLoginUrl()).toBe(
      `/login?reason=${SESSION_EXPIRED_REASON}&redirect=${encodeURIComponent('/workspace/chat')}`,
    )
    expect(buildForcedLoginUrl(SESSION_EXPIRED_REASON)).toContain(`reason=${SESSION_EXPIRED_REASON}`)
  })

  it('omits redirect when already on /login', () => {
    window.history.replaceState({}, '', '/login?tenant=acme')
    expect(buildSessionExpiredLoginUrl()).toBe(`/login?reason=${SESSION_EXPIRED_REASON}`)
  })

  it('clearStoredAuth removes both token keys', () => {
    localStorage.setItem('auth_token', 'tok')
    localStorage.setItem(AUTH_STORE_KEY, '{}')
    clearStoredAuth()
    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(localStorage.getItem(AUTH_STORE_KEY)).toBeNull()
  })

  it('redirectToSessionExpiredLogin clears auth before navigating', () => {
    localStorage.setItem('auth_token', 'tok')
    localStorage.setItem(AUTH_STORE_KEY, '{"state":{}}')

    const hrefValues: string[] = []
    const locationStub = {
      get pathname() {
        return '/workspace/chat'
      },
      get search() {
        return ''
      },
      get href() {
        return 'https://example.test/workspace/chat'
      },
      set href(value: string) {
        hrefValues.push(value)
      },
    }
    vi.stubGlobal('location', locationStub)

    redirectToSessionExpiredLogin()

    expect(localStorage.getItem('auth_token')).toBeNull()
    expect(localStorage.getItem(AUTH_STORE_KEY)).toBeNull()
    expect(hrefValues).toEqual([
      `/login?reason=${SESSION_EXPIRED_REASON}&redirect=${encodeURIComponent('/workspace/chat')}`,
    ])

    vi.unstubAllGlobals()
  })
})
