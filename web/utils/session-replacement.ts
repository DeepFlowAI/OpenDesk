export const AUTH_STORE_KEY = 'app-auth'
export const SESSION_REPLACED_CODE = 'SESSION_REPLACED'
export const SESSION_REPLACED_REASON = 'session_replaced'
/** Token/refresh invalid — not a concurrent login. */
export const SESSION_EXPIRED_REASON = 'session_expired'

export type ForcedLoginReason =
  | typeof SESSION_REPLACED_REASON
  | typeof SESSION_EXPIRED_REASON

export function isSessionReplacedCode(code: string | undefined | null): boolean {
  return code === SESSION_REPLACED_CODE
}

export function isForcedLoginReason(reason: string | null | undefined): reason is ForcedLoginReason {
  return reason === SESSION_REPLACED_REASON || reason === SESSION_EXPIRED_REASON
}

export async function readApiErrorCode(response: Response): Promise<string> {
  try {
    const body = (await response.clone().json()) as { code?: string }
    return body.code ?? ''
  } catch {
    return ''
  }
}

export function buildForcedLoginUrl(reason: ForcedLoginReason): string {
  const params = new URLSearchParams({ reason })
  if (typeof window !== 'undefined') {
    const redirect = `${window.location.pathname}${window.location.search}`
    if (redirect && !redirect.startsWith('/login')) {
      params.set('redirect', redirect)
    }
  }
  return `/login?${params.toString()}`
}

export function buildSessionReplacedLoginUrl(): string {
  return buildForcedLoginUrl(SESSION_REPLACED_REASON)
}

export function buildSessionExpiredLoginUrl(): string {
  return buildForcedLoginUrl(SESSION_EXPIRED_REASON)
}

export function clearStoredAuth() {
  localStorage.removeItem('auth_token')
  localStorage.removeItem(AUTH_STORE_KEY)
}

function assignForcedLogin(reason: ForcedLoginReason) {
  clearStoredAuth()
  window.location.href = buildForcedLoginUrl(reason)
}

export function redirectToSessionReplacedLogin() {
  assignForcedLogin(SESSION_REPLACED_REASON)
}

/** Invalid/expired credentials — show an honest "please sign in again" notice. */
export function redirectToSessionExpiredLogin() {
  assignForcedLogin(SESSION_EXPIRED_REASON)
}
