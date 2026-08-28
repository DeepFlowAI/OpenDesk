'use client'

import { useEffect } from 'react'
import { toast } from 'sonner'
import { useAuthStore } from '@/context/auth-store'
import { useLocaleStore } from '@/context/locale-store'
import { useTokenRefresh } from '@/hooks/use-token-refresh'
import { logAuthEvent } from '@/utils/auth-log'
import { t } from '@/utils/i18n'

const AUTH_STORE_KEY = 'app-auth'
const AUTH_TOKEN_KEY = 'auth_token'
// Survives the reload that adopts the account signed in by another tab.
const ACCOUNT_SWITCHED_KEY = 'opendesk_account_switched'

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

/**
 * A tab showing the login form owns its own auth flow: it may have just signed
 * in and be navigating into the app. Reloading it because another tab touched
 * shared storage throws that navigation away and drops the user back on an
 * empty login form.
 */
function ownsItsAuthFlow(): boolean {
  return window.location.pathname.startsWith('/login')
}

export function AuthSessionKeeper() {
  const { locale } = useLocaleStore()

  useTokenRefresh()

  useEffect(() => {
    let switched = false
    try {
      switched = sessionStorage.getItem(ACCOUNT_SWITCHED_KEY) === '1'
      if (switched) sessionStorage.removeItem(ACCOUNT_SWITCHED_KEY)
    } catch {
      // sessionStorage unavailable
    }
    if (switched) toast.info(t('auth.account_switched', locale))
  }, [locale])

  useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key === null) {
        if (!ownsItsAuthFlow()) window.location.reload()
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
      if (isSameIdentity(previous, next)) return

      if (ownsItsAuthFlow()) {
        void logAuthEvent('account_switch_reload_skipped')
        return
      }

      // Only one account is supported per browser: adopt the one that signed in
      // last, and tell the user why this tab changed under them.
      void logAuthEvent('account_switched', {
        previous_user_id: previous.userId ?? undefined,
        next_user_id: next.userId ?? undefined,
      })
      try {
        sessionStorage.setItem(ACCOUNT_SWITCHED_KEY, '1')
      } catch {
        // sessionStorage unavailable
      }
      window.location.reload()
    }

    window.addEventListener('storage', handleStorage)
    return () => window.removeEventListener('storage', handleStorage)
  }, [])

  return null
}
