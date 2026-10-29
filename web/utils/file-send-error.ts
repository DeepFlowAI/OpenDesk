import { HTTPError } from 'ky'

const MAX_ERROR_MESSAGE_LEN = 200

export function isEmptyUploadFile(file: Pick<File, 'size'>): boolean {
  return file.size === 0
}

/** Best-effort business `code` from a ky HTTPError body; null when unavailable. */
export async function readBusinessErrorCode(error: unknown): Promise<string | null> {
  if (!(error instanceof HTTPError)) return null
  try {
    const body = (await error.response.clone().json()) as { code?: string }
    if (typeof body.code === 'string' && body.code.trim()) {
      return body.code.trim()
    }
  } catch {
    // ignore JSON parse errors
  }
  return null
}

/** Best-effort reason for file_send_failed telemetry. Keep it short and stable. */
export async function describeFileSendError(error: unknown): Promise<string> {
  if (error instanceof HTTPError) {
    try {
      const body = (await error.response.clone().json()) as {
        message?: string
        detail?: string | Array<{ msg?: string }>
      }
      if (typeof body.message === 'string' && body.message.trim()) {
        return body.message.trim().slice(0, MAX_ERROR_MESSAGE_LEN)
      }
      if (typeof body.detail === 'string' && body.detail.trim()) {
        return body.detail.trim().slice(0, MAX_ERROR_MESSAGE_LEN)
      }
      if (Array.isArray(body.detail)) {
        const first = body.detail.find((item) => typeof item?.msg === 'string' && item.msg.trim())
        if (first?.msg) return first.msg.trim().slice(0, MAX_ERROR_MESSAGE_LEN)
      }
    } catch {
      // ignore JSON parse errors
    }
    return `http_${error.response.status}`
  }
  if (error instanceof Error && error.message.trim()) {
    return error.message.trim().slice(0, MAX_ERROR_MESSAGE_LEN)
  }
  return 'unknown'
}
