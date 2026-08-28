const CRAWLER_UA =
  /bot|crawler|spider|facebookexternalhit|meta-externalagent|whatsapp|slackbot|twitterbot|linkedinbot/i

const RESIZE_OBSERVER_NOISE =
  /ResizeObserver loop (completed with undelivered notifications|limit exceeded)/i

const BEST_EFFORT_CONTROL_RELEASE = /401.*embed\/control\/release/i

export function isCrawlerUserAgent(userAgent: string | undefined): boolean {
  if (!userAgent) return false
  return CRAWLER_UA.test(userAgent)
}

function errorMessage(error: unknown): string {
  if (typeof error === 'string') return error
  if (error instanceof Error) return error.message
  if (error && typeof error === 'object' && 'message' in error) {
    const message = (error as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  return String(error ?? '')
}

function requestUrl(error: unknown): string {
  if (!error || typeof error !== 'object' || !('request' in error)) return ''
  const url = (error as { request?: { url?: string } }).request?.url
  return typeof url === 'string' ? url : ''
}

function responseStatus(error: unknown): number | undefined {
  if (!error || typeof error !== 'object' || !('response' in error)) return undefined
  const status = (error as { response?: { status?: number } }).response?.status
  return typeof status === 'number' ? status : undefined
}

/**
 * Browser / cleanup noise that should not page as a client crash.
 * ResizeObserver notifications are a Chromium quirk; embed control release
 * after logout is best-effort because the short lease expires on its own.
 */
export function isIgnorableClientError(error: unknown): boolean {
  if (!error) return false
  const message = errorMessage(error)
  if (RESIZE_OBSERVER_NOISE.test(message)) return true
  if (BEST_EFFORT_CONTROL_RELEASE.test(message)) return true
  return responseStatus(error) === 401 && requestUrl(error).includes('embed/control/release')
}
