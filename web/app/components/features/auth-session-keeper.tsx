'use client'

import { useEffect } from 'react'
import { useAuthStore } from '@/context/auth-store'
import { useTokenRefresh } from '@/hooks/use-token-refresh'
import { logAuthEvent } from '@/utils/auth-log'

const AUTH_STORE_KEY = 'app-auth'
const AUTH_TOKEN_KEY = 'auth_token'

type AuthIdentity = {
  userId: number | null
  tenantId: number | null
}

type PersistedAuthStore = {
  state?: {
    user?: {
      id?: unknown
      tenant_id?: unknown
    } | null
  }
}

function normalizeId(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

function readAuthIdentity(raw: string | null): AuthIdentity {
  if (!raw) return { userId: null, tenantId: null }
  try {
    const parsed = JSON.parse(raw) as PersistedAuthStore
    const user = parsed.state?.user
    return {
      userId: normalizeId(user?.id),
      tenantId: normalizeId(user?.tenant_id),
    }
  } catch {
    return { userId: null, tenantId: null }
  }
}

function isSameIdentity(a: AuthIdentity, b: AuthIdentity): boolean {
  return a.userId === b.userId && a.tenantId === b.tenantId
}

export function AuthSessionKeeper() {
  useTokenRefresh()

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key === null) {
        window.location.reload()
        return
      }

      // Same user re-logged in another tab: silently pick up the new token
      // without a full reload so the socket/API can keep working.
      if (event.key === AUTH_TOKEN_KEY) {
        const nextToken = event.newValue
        if (typeof nextToken === 'string' && nextToken && nextToken !== useAuthStore.getState().token) {
          useAuthStore.setState({ token: nextToken })
          void logAuthEvent('token_adopted_from_storage')
        }
        return
      }

      if (event.key !== AUTH_STORE_KEY) return

      const previous = readAuthIdentity(event.oldValue)
      const next = readAuthIdentity(event.newValue)
      if (!isSameIdentity(previous, next)) {
        window.location.reload()
      }
    }

    window.addEventListener('storage', handleStorage)
    return () => window.removeEventListener('storage', handleStorage)
  }, [])

  return null
}
