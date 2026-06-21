'use client'

import { useEffect, useRef } from 'react'
import { useAuthStore } from '@/context/auth-store'
import { refreshAccessToken } from '@/service/base'
import { logAuthEvent } from '@/utils/auth-log'

// Re-evaluate whether the token needs refreshing on a short tick. Using a
// repeating check (instead of a single long timer) survives background-tab
// timer throttling and self-corrects as soon as the tab regains focus.
const CHECK_INTERVAL_MS = 60 * 1000 // 1 minute

// Begin renewing this long before the token actually expires. This window also
// doubles as the retry budget: transient failures keep retrying every tick
// until a refresh succeeds or the token finally expires.
const REFRESH_LEAD_MS = 10 * 60 * 1000 // 10 minutes

/** Read the `exp` claim (ms epoch) from a JWT without verifying its signature. */
function readTokenExpiry(token: string): number | null {
  const parts = token.split('.')
  if (parts.length !== 3) return null
  try {
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
    const payload = JSON.parse(atob(padded)) as { exp?: number }
    return typeof payload.exp === 'number' ? payload.exp * 1000 : null
  } catch {
    return null
  }
}

/**
 * Keep the JWT fresh while the user is active, following the common
 * proactive-refresh pattern:
 *  - silently renew shortly before expiry (driven by the token's own `exp`,
 *    not a fixed clock);
 *  - distinguish auth failures (401/403 → log out) from transient
 *    network/server errors (keep the session and retry on the next tick);
 *  - only force a logout once the token has actually expired.
 */
export function useTokenRefresh() {
  const token = useAuthStore((state) => state.token)
  const user = useAuthStore((state) => state.user)
  const refreshingRef = useRef(false)

  useEffect(() => {
    if (!token || !user) return

    const tick = async () => {
      if (refreshingRef.current) return
      const current = useAuthStore.getState().token
      if (!current) return

      const expiresAt = readTokenExpiry(current)
      // Can't read expiry → leave renewal to the reactive 401 handler.
      if (expiresAt === null) return

      const now = Date.now()
      if (now >= expiresAt) {
        // Token is already dead; a silent refresh is no longer possible.
        await logAuthEvent('session_cleared', { trigger: 'token_expired' }, { immediate: true })
        useAuthStore.getState().clearAuth()
        return
      }
      // Still outside the renewal window → nothing to do yet.
      if (now < expiresAt - REFRESH_LEAD_MS) return

      refreshingRef.current = true
      try {
        const outcome = await refreshAccessToken()
        const { user: currentUser, setAuth, clearAuth } = useAuthStore.getState()
        if (outcome.status === 'success' && currentUser) {
          setAuth(currentUser, outcome.token)
        } else if (outcome.status === 'auth_error' || outcome.status === 'no_token') {
          await logAuthEvent('session_cleared', { trigger: 'periodic_refresh_auth_error' }, { immediate: true })
          clearAuth()
        }
        // transient_error → keep the session; the next tick retries while there
        // is still time left before the token expires.
      } finally {
        refreshingRef.current = false
      }
    }

    void tick()
    const timer = setInterval(() => void tick(), CHECK_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [token, user])
}
