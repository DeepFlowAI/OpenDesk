'use client'

import { useEffect, useRef } from 'react'
import { useAuthStore } from '@/context/auth-store'
import { getRefreshFailureState, refreshAccessToken } from '@/service/base'
import { logAuthEvent } from '@/utils/auth-log'
import { adoptNewerTokenIfAny, readStoredToken } from '@/utils/auth-session'
import {
  SESSION_EXPIRED_REASON,
  SESSION_REPLACED_REASON,
  redirectToSessionExpiredLogin,
  redirectToSessionReplacedLogin,
} from '@/utils/session-replacement'

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
        // Another tab may have logged in again with a newer token — don't
        // wipe that shared session.
        if (adoptNewerTokenIfAny(current)) {
          await logAuthEvent('session_clear_skipped', { trigger: 'token_expired' }, { immediate: true })
          return
        }
        const failure = getRefreshFailureState()
        await logAuthEvent(
          'session_cleared',
          {
            trigger: 'token_expired',
            redirect_reason: SESSION_EXPIRED_REASON,
            consecutive_failures: failure.consecutiveFailures,
            last_status: failure.lastStatus ?? undefined,
            last_reason: failure.lastReason ?? undefined,
            token_exp: new Date(expiresAt).toISOString(),
            client_now: new Date(now).toISOString(),
            expired_for_ms: now - expiresAt,
          },
          { immediate: true },
        )
        // Hard-navigate with a notice — clearAuth alone lets layout soft-replace
        // to bare /login with no explanation (silent flash).
        redirectToSessionExpiredLogin()
        return
      }
      // Still outside the renewal window → nothing to do yet.
      if (now < expiresAt - REFRESH_LEAD_MS) return

      // Capture the token we are about to refresh so a concurrent login in
      // another tab can be detected if this attempt fails.
      const tokenBeforeRefresh = readStoredToken()
      refreshingRef.current = true
      try {
        const outcome = await refreshAccessToken()
        const { user: currentUser, setAuth } = useAuthStore.getState()
        if (outcome.status === 'success' && currentUser) {
          setAuth(currentUser, outcome.token)
        } else if (outcome.status === 'session_replaced') {
          if (adoptNewerTokenIfAny(tokenBeforeRefresh)) {
            await logAuthEvent(
              'session_clear_skipped',
              { trigger: 'periodic_refresh_session_replaced' },
              { immediate: true },
            )
            return
          }
          await logAuthEvent(
            'session_cleared',
            {
              trigger: 'periodic_refresh_session_replaced',
              redirect_reason: SESSION_REPLACED_REASON,
              refresh_outcome: outcome.status,
            },
            { immediate: true },
          )
          redirectToSessionReplacedLogin()
        } else if (outcome.status === 'auth_error' || outcome.status === 'no_token') {
          if (adoptNewerTokenIfAny(tokenBeforeRefresh)) {
            await logAuthEvent(
              'session_clear_skipped',
              { trigger: 'periodic_refresh_auth_error' },
              { immediate: true },
            )
            return
          }
          await logAuthEvent(
            'session_cleared',
            {
              trigger: 'periodic_refresh_auth_error',
              redirect_reason: SESSION_EXPIRED_REASON,
              refresh_outcome: outcome.status,
            },
            { immediate: true },
          )
          redirectToSessionExpiredLogin()
        }
        // transient_error → keep the session; the next tick retries while there
        // is still time left before the token expires.
      } finally {
        refreshingRef.current = false
      }
    }

    const onVisible = () => {
      if (document.visibilityState === 'visible') void tick()
    }
    const onWake = () => {
      void tick()
    }

    void tick()
    const timer = setInterval(() => void tick(), CHECK_INTERVAL_MS)
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onWake)
    window.addEventListener('online', onWake)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onWake)
      window.removeEventListener('online', onWake)
    }
  }, [token, user])
}
