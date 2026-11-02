import ky, { HTTPError } from 'ky'
import { normalizeApiBase } from '@/service/base'

// The tenant console has its own admin session, separate from employee login.
export const TENANT_CONSOLE_TOKEN_KEY = 'tenant_console_token'
export const TENANT_CONSOLE_LOGIN_PATH = '/tenant/login'

const API_BASE = normalizeApiBase(process.env.NEXT_PUBLIC_API_URL)

export function readConsoleToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TENANT_CONSOLE_TOKEN_KEY)
}

export function saveConsoleToken(token: string): void {
  localStorage.setItem(TENANT_CONSOLE_TOKEN_KEY, token)
}

export function clearConsoleToken(): void {
  localStorage.removeItem(TENANT_CONSOLE_TOKEN_KEY)
}

function redirectToConsoleLogin(): void {
  clearConsoleToken()
  if (!window.location.pathname.startsWith(TENANT_CONSOLE_LOGIN_PATH)) {
    window.location.replace(TENANT_CONSOLE_LOGIN_PATH)
  }
}

export const consoleClient = ky.create({
  prefixUrl: API_BASE,
  timeout: 30000,
  hooks: {
    beforeRequest: [
      (request) => {
        const token = readConsoleToken()
        if (token) request.headers.set('Authorization', `Bearer ${token}`)
      },
    ],
    afterResponse: [
      (request, _options, response) => {
        if (response.status === 401 && !request.url.includes('/tenant-console/auth/login')) {
          redirectToConsoleLogin()
        }
      },
    ],
  },
})

export const consoleGet = <T>(url: string, options?: Parameters<typeof consoleClient.get>[1]) =>
  consoleClient.get(url, options).json<T>()

export const consolePost = <T>(url: string, options?: Parameters<typeof consoleClient.post>[1]) =>
  consoleClient.post(url, options).json<T>()

export const consolePut = <T>(url: string, options?: Parameters<typeof consoleClient.put>[1]) =>
  consoleClient.put(url, options).json<T>()

export const consolePatch = <T>(url: string, options?: Parameters<typeof consoleClient.patch>[1]) =>
  consoleClient.patch(url, options).json<T>()

export const consoleDelete = async (url: string): Promise<void> => {
  await consoleClient.delete(url)
}

/** Download a CSV export and save it with the server-provided filename. */
export async function consoleDownload(
  url: string,
  searchParams: Record<string, string>,
  fallbackName: string,
): Promise<void> {
  const response = await consoleClient.get(url, { searchParams })
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') ?? ''
  const match = /filename="([^"]+)"/i.exec(disposition)
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = match?.[1] ?? fallbackName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

/** Best-effort human-readable message from an API error response. */
export async function readConsoleError(error: unknown, fallback: string): Promise<string> {
  if (!(error instanceof HTTPError)) return fallback
  try {
    const body = (await error.response.clone().json()) as {
      message?: unknown
      detail?: unknown
    }
    if (typeof body.message === 'string' && body.message) return body.message
    if (Array.isArray(body.detail) && body.detail.length > 0) {
      const first = body.detail[0] as { msg?: unknown }
      if (typeof first.msg === 'string') return first.msg
    }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    // Non-JSON error body.
  }
  return fallback
}

export function isConsoleHttpStatus(error: unknown, status: number): boolean {
  return error instanceof HTTPError && error.response.status === status
}
