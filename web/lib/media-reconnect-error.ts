import { HTTPError } from 'ky'

/** True when media-reconnect failed because the customer call already ended. */
export async function isCurrentCallGoneError(error: unknown): Promise<boolean> {
  if (!(error instanceof HTTPError)) {
    const msg = error instanceof Error ? error.message : String(error)
    return /404/.test(msg) && /media-reconnect/.test(msg)
  }
  if (error.response.status === 404) return true
  try {
    const body = (await error.response.clone().json()) as {
      code?: string
      message?: string
    }
    if (body.code === 'NOT_FOUND') return true
    const message = body.message ?? ''
    return (
      message.includes('当前没有进行中的通话') ||
      message.includes('当前通话状态已变化')
    )
  } catch {
    return false
  }
}
