import { HTTPError } from 'ky'

/** Best-effort extract of a human-readable API error for employee save toasts. */
export async function readEmployeeErrorMessage(
  error: unknown,
  fallback: string,
): Promise<string> {
  if (!(error instanceof HTTPError)) return fallback
  try {
    const body = (await error.response.json()) as {
      message?: string
      detail?: string | Array<{ msg?: string }>
    }
    if (typeof body.message === 'string' && body.message.trim()) {
      return body.message.trim()
    }
    if (typeof body.detail === 'string' && body.detail.trim()) {
      return body.detail.trim()
    }
    if (Array.isArray(body.detail)) {
      const first = body.detail.find((item) => typeof item?.msg === 'string' && item.msg.trim())
      if (first?.msg) return first.msg.trim()
    }
  } catch {
    // ignore JSON parse errors
  }
  return fallback
}
