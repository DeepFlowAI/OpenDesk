'use client'

import { useEffect } from 'react'
import { useTokenRefresh } from '@/hooks/use-token-refresh'

const AUTH_STORE_KEY = 'app-auth'

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
