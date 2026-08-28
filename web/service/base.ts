import ky, { HTTPError } from 'ky'
import { logAuthEvent } from '@/utils/auth-log'
import { adoptNewerTokenIfAny, readStoredToken } from '@/utils/auth-session'
import {
  SESSION_EXPIRED_REASON,
  SESSION_REPLACED_REASON,
  isSessionReplacedCode,
  readApiErrorCode,
  redirectToSessionExpiredLogin,
  redirectToSessionReplacedLogin,
} from '@/utils/session-replacement'

/** Strip trailing slashes so manual URL joins never produce `//` path segments. */
export function normalizeApiBase(raw: string | undefined): string {
  return (raw ?? '').replace(/\/+$/, '')
}

// API base URL must be supplied via NEXT_PUBLIC_API_URL (see web/.env.example).
// We intentionally avoid a hard-coded localhost fallback so production builds
// never silently target an internal/dev address.
const API_BASE = normalizeApiBase(process.env.NEXT_PUBLIC_API_URL)

let runtimeAccessToken: string | null = null

/** Short-lived token for isolated surfaces such as the embedded call iframe. */
export function setRuntimeAccessToken(token: string | null): void {
  runtimeAccessToken = token
}

/**
 * Result of a token refresh attempt.
 * - `success`: a fresh token was issued.
 * - `auth_error`: the server rejected the credentials (401/403) — the session
 *   is genuinely invalid and the user must re-authenticate.
 * - `session_replaced`: a newer login replaced this session.
 * - `transient_error`: a network/server-side hiccup (timeout, 5xx, 429) — the
 *   existing session may still be valid, so callers should retry rather than
 *   force a logout.
 * - `no_token`: there is no stored token to refresh.
 */
export type RefreshOutcome =
  | { status: 'success'; token: string }
  | { status: 'auth_error' }
  | { status: 'session_replaced' }
  | { status: 'transient_error' }
  | { status: 'no_token' }

export type RefreshFailureState = {
  consecutiveFailures: number
  lastStatus: number | null
  lastReason: string | null
}

let refreshFailureState: RefreshFailureState = {
  consecutiveFailures: 0,
  lastStatus: null,
  lastReason: null,
}

/** Snapshot of recent refresh failures (for logout diagnostics). */
export function getRefreshFailureState(): Readonly<RefreshFailureState> {
  return refreshFailureState
}

function recordRefreshFailure(status: number | null, reason: string) {
  refreshFailureState = {
    consecutiveFailures: refreshFailureState.consecutiveFailures + 1,
    lastStatus: status,
    lastReason: reason,
  }
}

function clearRefreshFailures() {
  refreshFailureState = {
    consecutiveFailures: 0,
    lastStatus: null,
    lastReason: null,
  }
}

function bearerTokenFromRequest(request: Request): string | null {
  const header = request.headers.get('Authorization')
  if (!header?.startsWith('Bearer ')) return null
  return header.slice('Bearer '.length)
}

/**
 * Auth endpoints that return 401 for bad credentials (not an expired session).
 * The global afterResponse hook must not clear storage / reload on these.
 */
export function isCredentialChallengeUrl(url: string): boolean {
  return (
    url.includes('/auth/login') ||
    url.includes('/auth/sso') ||
    url.includes('/auth/send-verify-code') ||
    url.includes('/auth/reset-password')
  )
}

/**
 * Skip clearing the shared session when another tab already replaced the token.
 * Returns true when the logout was skipped.
 */
async function skipClearIfNewerToken(
  staleToken: string | null,
  trigger: string,
  path?: string,
): Promise<boolean> {
  if (!adoptNewerTokenIfAny(staleToken)) return false
  await logAuthEvent(
    'session_clear_skipped',
    { trigger, ...(path ? { path } : {}) },
    { immediate: true },
  )
  return true
}

let refreshPromise: Promise<RefreshOutcome> | null = null

/**
 * Try to exchange the current token for a fresh one.
 * Deduplicates concurrent calls so only one refresh request flies at a time.
 */
export async function refreshAccessToken(): Promise<RefreshOutcome> {
  if (refreshPromise) return refreshPromise

  refreshPromise = (async (): Promise<RefreshOutcome> => {
    const token = localStorage.getItem('auth_token')
    if (!token) return { status: 'no_token' }
    const refreshUrl = `${API_BASE}/v1/auth/refresh`
    try {
      const res = await ky
        .post(refreshUrl, {
          headers: { Authorization: `Bearer ${token}` },
          timeout: 10000,
        })
        .json<{ access_token: string }>()
      localStorage.setItem('auth_token', res.access_token)
      clearRefreshFailures()
      logAuthEvent('token_refresh_succeeded')
      return { status: 'success', token: res.access_token }
    } catch (err) {
      if (err instanceof HTTPError) {
        const status = err.response.status
        const code = await readApiErrorCode(err.response)
        let serverMessage = ''
        try {
          const body = (await err.response.json()) as { message?: string }
          serverMessage = body.message ?? ''
        } catch {
          // ignore JSON parse errors
        }
        const reason = serverMessage || 'http_error'
        recordRefreshFailure(status, reason)
        // Non-auth HTTP failures (404, 5xx, …) usually mean misconfig/deploy
        // issues, not brief network blips — surface them at error level.
        const isAuthRejection = status === 401 || status === 403
        logAuthEvent(
          'token_refresh_failed',
          { status, reason, url: refreshUrl },
          isAuthRejection ? undefined : { level: 'error' },
        )
        if (isAuthRejection && isSessionReplacedCode(code)) {
          return { status: 'session_replaced' }
        }
        // Only 401/403 mean the credentials are truly invalid; any other
        // status (5xx, 429, ...) is treated as a retryable transient failure.
        if (isAuthRejection) return { status: 'auth_error' }
        return { status: 'transient_error' }
      }
      // Network error / timeout — retryable, don't drop the session.
      recordRefreshFailure(null, 'network_or_unknown')
      logAuthEvent('token_refresh_failed', {
        reason: 'network_or_unknown',
        url: refreshUrl,
      })
      return { status: 'transient_error' }
    } finally {
      refreshPromise = null
    }
  })()
  return refreshPromise
}

const client = ky.create({
  prefixUrl: API_BASE,
  timeout: 30000,
  hooks: {
    beforeRequest: [
      (request) => {
        const token = runtimeAccessToken || localStorage.getItem('auth_token')
        if (token) request.headers.set('Authorization', `Bearer ${token}`)
      },
    ],
    afterResponse: [
      async (request, _options, response) => {
        if (response.status !== 401) return
        const requestToken = bearerTokenFromRequest(request)
        if (runtimeAccessToken && requestToken === runtimeAccessToken) return
        // Wrong password / SSO / reset-password 401s must reach the page
        // error UI. Do not treat them as session expiry (which reloads /login
        // and flashes away the "invalid credentials" message).
        if (isCredentialChallengeUrl(request.url)) return
        const code = await readApiErrorCode(response)
        if (isSessionReplacedCode(code)) {
          if (await skipClearIfNewerToken(requestToken, 'session_replaced', request.url)) return
          await logAuthEvent('session_cleared', {
            trigger: 'session_replaced',
            path: request.url,
            redirect_reason: SESSION_REPLACED_REASON,
            api_error_code: code,
          }, { immediate: true })
          redirectToSessionReplacedLogin()
          return
        }
        // Don't retry the refresh endpoint itself
        if (request.url.includes('/auth/refresh')) {
          if (await skipClearIfNewerToken(requestToken, 'refresh_endpoint_401', request.url)) return
          await logAuthEvent('session_cleared', {
            trigger: 'refresh_endpoint_401',
            path: request.url,
            redirect_reason: SESSION_EXPIRED_REASON,
            api_error_code: code,
          }, { immediate: true })
          redirectToSessionExpiredLogin()
          return
        }
        logAuthEvent('api_unauthorized', { path: request.url, api_error_code: code })
        // refreshAccessToken reads localStorage — capture that token so the
        // post-refresh clear gate compares against what was actually refreshed,
        // not the (possibly older) Authorization header on this request.
        const tokenBeforeRefresh = readStoredToken()
        const outcome = await refreshAccessToken()
        if (outcome.status === 'success') {
          // Retry the original request with the fresh token
          request.headers.set('Authorization', `Bearer ${outcome.token}`)
          return ky(request)
        }
        // Transient refresh failure (network/5xx): let the original 401 surface
        // to the caller, but keep the session so a temporary hiccup doesn't
        // kick the user out.
        if (outcome.status === 'transient_error') return
        if (outcome.status === 'session_replaced') {
          if (await skipClearIfNewerToken(tokenBeforeRefresh, 'refresh_session_replaced', request.url)) return
          await logAuthEvent('session_cleared', {
            trigger: 'refresh_session_replaced',
            path: request.url,
            redirect_reason: SESSION_REPLACED_REASON,
            refresh_outcome: outcome.status,
          }, { immediate: true })
          redirectToSessionReplacedLogin()
          return
        }
        // auth_error / no_token: credentials are invalid → force re-login.
        if (await skipClearIfNewerToken(tokenBeforeRefresh, 'refresh_after_api_401', request.url)) return
        await logAuthEvent('session_cleared', {
          trigger: 'refresh_after_api_401',
          path: request.url,
          redirect_reason: SESSION_EXPIRED_REASON,
          refresh_outcome: outcome.status,
          api_error_code: code,
        }, { immediate: true })
        redirectToSessionExpiredLogin()
        return
      },
    ],
  },
})

export const get = <T>(url: string, options?: Parameters<typeof client.get>[1]) =>
  client.get(url, options).json<T>()

export const getBlob = async (url: string, options?: Parameters<typeof client.get>[1]) => {
  const response = await client.get(url, options)
  return { blob: await response.blob(), headers: response.headers }
}

export const postBlob = async (url: string, options?: Parameters<typeof client.post>[1]) => {
  const response = await client.post(url, options)
  return { blob: await response.blob(), headers: response.headers }
}

export function filenameFromContentDisposition(value: string | null, fallback: string): string {
  if (!value) return fallback

  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(value)
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1])
    } catch {
      return encoded[1]
    }
  }

  const quoted = /filename="([^"]+)"/i.exec(value)
  if (quoted?.[1]) return quoted[1]
  return fallback
}

export const post = <T>(url: string, options?: Parameters<typeof client.post>[1]) =>
  client.post(url, options).json<T>()

/** Multipart upload — uses same base URL and auth hooks as other API calls */
export const postForm = <T>(url: string, formData: FormData, timeoutMs = 60000) =>
  client.post(url, { body: formData, timeout: timeoutMs }).json<T>()

export const put = <T>(url: string, options?: Parameters<typeof client.put>[1]) =>
  client.put(url, options).json<T>()

export const patch = <T>(url: string, options?: Parameters<typeof client.patch>[1]) =>
  client.patch(url, options).json<T>()

export const del = <T = void>(url: string, options?: Parameters<typeof client.delete>[1]) =>
  client.delete(url, options).json<T>()
