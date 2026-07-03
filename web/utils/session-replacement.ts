export const AUTH_STORE_KEY = 'app-auth'
export const SESSION_REPLACED_CODE = 'SESSION_REPLACED'
export const SESSION_REPLACED_REASON = 'session_replaced'

export function isSessionReplacedCode(code: string | undefined | null): boolean {
  return code === SESSION_REPLACED_CODE
}

export async function readApiErrorCode(response: Response): Promise<string> {
  try {
    const body = (await response.clone().json()) as { code?: string }
    return body.code ?? ''
  } catch {
    return ''
  }
}

export function buildSessionReplacedLoginUrl(): string {
  const params = new URLSearchParams({ reason: SESSION_REPLACED_REASON })
  if (typeof window !== 'undefined') {
    const redirect = `${window.location.pathname}${window.location.search}`
    if (redirect && !redirect.startsWith('/login')) {
      params.set('redirect', redirect)
    }
  }
  return `/login?${params.toString()}`
}

export function clearStoredAuth() {
  localStorage.removeItem('auth_token')
  localStorage.removeItem(AUTH_STORE_KEY)
}

export function redirectToSessionReplacedLogin() {
  clearStoredAuth()
  window.location.href = buildSessionReplacedLoginUrl()
}
