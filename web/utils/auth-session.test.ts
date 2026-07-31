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

import { useAuthStore } from '@/context/auth-store'
import { adoptNewerTokenIfAny, readStoredToken } from '@/utils/auth-session'

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({ user: null, token: null })
})

describe('readStoredToken', () => {
  it('reads auth_token from localStorage', () => {
    localStorage.setItem('auth_token', 'stored-token')
    expect(readStoredToken()).toBe('stored-token')
  })
})

describe('adoptNewerTokenIfAny', () => {
  it('adopts a newer stored token and updates the auth store', () => {
    localStorage.setItem('auth_token', 'fresh-token')
    useAuthStore.setState({ token: 'stale-token' })

    expect(adoptNewerTokenIfAny('stale-token')).toBe(true)
    expect(useAuthStore.getState().token).toBe('fresh-token')
  })

  it('returns false when stored token matches the stale token', () => {
    localStorage.setItem('auth_token', 'same-token')
    useAuthStore.setState({ token: 'same-token' })

    expect(adoptNewerTokenIfAny('same-token')).toBe(false)
    expect(useAuthStore.getState().token).toBe('same-token')
  })

  // After refreshAccessToken fails, storage still holds the token that was
  // refreshed. Comparing against that token (not the older request header)
  // must not skip session clear.
  it('does not skip clear when the refreshed token itself was rejected', () => {
    localStorage.setItem('auth_token', 'token-used-for-refresh')
    useAuthStore.setState({ token: 'older-request-token' })

    expect(adoptNewerTokenIfAny('token-used-for-refresh')).toBe(false)
    expect(useAuthStore.getState().token).toBe('older-request-token')
  })

  it('returns false when there is no stored token', () => {
    useAuthStore.setState({ token: 'stale-token' })
    expect(adoptNewerTokenIfAny('stale-token')).toBe(false)
  })

  it('returns false when staleToken is empty', () => {
    localStorage.setItem('auth_token', 'fresh-token')
    expect(adoptNewerTokenIfAny(null)).toBe(false)
    expect(adoptNewerTokenIfAny('')).toBe(false)
    expect(useAuthStore.getState().token).toBeNull()
  })
})
