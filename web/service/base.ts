import ky, { HTTPError } from 'ky'
import { logAuthEvent } from '@/utils/auth-log'

// API base URL must be supplied via NEXT_PUBLIC_API_URL (see web/.env.example).
// We intentionally avoid a hard-coded localhost fallback so production builds
// never silently target an internal/dev address.
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? ''

/**
 * Result of a token refresh attempt.
 * - `success`: a fresh token was issued.
 * - `auth_error`: the server rejected the credentials (401/403) — the session
 *   is genuinely invalid and the user must re-authenticate.
 * - `transient_error`: a network/server-side hiccup (timeout, 5xx, 429) — the
 *   existing session may still be valid, so callers should retry rather than
 *   force a logout.
 * - `no_token`: there is no stored token to refresh.
 */
export type RefreshOutcome =
  | { status: 'success'; token: string }
  | { status: 'auth_error' }
  | { status: 'transient_error' }
  | { status: 'no_token' }

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
    try {
      const res = await ky
        .post(`${API_BASE}/v1/auth/refresh`, {
          headers: { Authorization: `Bearer ${token}` },
          timeout: 10000,
        })
        .json<{ access_token: string }>()
      localStorage.setItem('auth_token', res.access_token)
      logAuthEvent('token_refresh_succeeded')
      return { status: 'success', token: res.access_token }
    } catch (err) {
      if (err instanceof HTTPError) {
        const status = err.response.status
        let serverMessage = ''
        try {
          const body = (await err.response.json()) as { message?: string }
          serverMessage = body.message ?? ''
        } catch {
          // ignore JSON parse errors
        }
        logAuthEvent('token_refresh_failed', {
          status,
          reason: serverMessage || 'http_error',
        })
        // Only 401/403 mean the credentials are truly invalid; any other
        // status (5xx, 429, ...) is treated as a retryable transient failure.
        if (status === 401 || status === 403) return { status: 'auth_error' }
        return { status: 'transient_error' }
      }
      // Network error / timeout — retryable, don't drop the session.
      logAuthEvent('token_refresh_failed', { reason: 'network_or_unknown' })
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
        const token = localStorage.getItem('auth_token')
        if (token) request.headers.set('Authorization', `Bearer ${token}`)
      },
    ],
    afterResponse: [
      async (request, _options, response) => {
        if (response.status !== 401) return
        // Don't retry the refresh endpoint itself
        if (request.url.includes('/auth/refresh')) {
          await logAuthEvent('session_cleared', {
            trigger: 'refresh_endpoint_401',
            path: request.url,
          }, { immediate: true })
          localStorage.removeItem('auth_token')
          window.location.href = '/login'
          return
        }
        logAuthEvent('api_unauthorized', { path: request.url })
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
        // auth_error / no_token: credentials are invalid → force re-login.
        await logAuthEvent('session_cleared', {
          trigger: 'refresh_after_api_401',
          path: request.url,
        }, { immediate: true })
        localStorage.removeItem('auth_token')
        window.location.href = '/login'
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
