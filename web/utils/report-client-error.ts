import { isChunkLoadError } from '@/lib/chunk-load-error'
import { isCrawlerUserAgent, isIgnorableClientError } from '@/lib/client-error-filters'
import { telemetry } from '@/service/telemetry'

export type ClientErrorEvent =
  | 'app_render_crashed'
  | 'app_unhandled_error'
  | 'app_unhandled_rejection'

type ClientErrorContext = Record<string, string | number | boolean | undefined>

// Ingest keeps only the first 256 characters of any single property value, so a
// stack is split across numbered properties to preserve enough frames to act on.
const STACK_CHUNK_CHARS = 256
const MAX_STACK_CHUNKS = 4
// A failing render can retry in a loop; cap what a single page load may send.
const MAX_REPORTS_PER_PAGE = 10

let reportCount = 0
const reportedSignatures = new Set<string>()

function describeError(error: unknown): { name: string; message: string; stack: string } {
  if (error instanceof Error) {
    return { name: error.name, message: error.message, stack: error.stack ?? '' }
  }
  return { name: typeof error, message: String(error), stack: '' }
}

function toStackProps(stack: string): Record<string, string> {
  const props: Record<string, string> = {}
  for (let index = 0; index < MAX_STACK_CHUNKS; index += 1) {
    const chunk = stack.slice(index * STACK_CHUNK_CHARS, (index + 1) * STACK_CHUNK_CHARS)
    if (!chunk) break
    props[`stack_${index}`] = chunk
  }
  return props
}

/**
 * Sends an uncaught client-side failure to telemetry and flushes immediately,
 * because the page it came from is often about to be torn down. Chunk-load
 * misses after a deploy are reported as warnings; crawler hits are ignored.
 */
export async function reportClientError(
  event: ClientErrorEvent,
  error: unknown,
  context?: ClientErrorContext,
): Promise<void> {
  if (typeof navigator !== 'undefined' && isCrawlerUserAgent(navigator.userAgent)) return
  if (isIgnorableClientError(error)) return

  const { name, message, stack } = describeError(error)
  const signature = `${event}|${name}|${message}|${stack.slice(0, STACK_CHUNK_CHARS)}`
  if (reportedSignatures.has(signature) || reportCount >= MAX_REPORTS_PER_PAGE) return
  reportedSignatures.add(signature)
  reportCount += 1

  const props: Record<string, string | number | boolean> = {
    error_name: name,
    error_message: message,
    ...toStackProps(stack),
  }
  for (const [key, value] of Object.entries(context ?? {})) {
    if (value !== undefined) props[key] = value
  }

  const level = isChunkLoadError(error) ? 'warn' : 'error'
  console.error(`[client-error] ${event}`, error)
  telemetry.trackApp(event, { level, props })
  await telemetry.flushApp()
}
