import type { TelemetryLevel } from '@/models/telemetry'

export const RECOVERABLE_VISITOR_SESSION_CODES = [
  'UNAUTHORIZED',
  'visitor_session_required',
] as const

export type VisitorRecoverableErrorContext = 'http' | 'socket_join' | 'socket_connect'

const RECOVERABLE_MESSAGE_FRAGMENTS = [
  'invalid or expired visitor session',
  'invalid visitor session',
  'visitor_session_required',
  'visitor_session_token',
] as const

type ErrorRecord = {
  message?: unknown
  error?: unknown
  code?: unknown
  detail?: unknown
  response?: { status?: unknown }
}

function asRecord(error: unknown): ErrorRecord | null {
  return error && typeof error === 'object' ? error as ErrorRecord : null
}

function readHttpStatus(error: unknown, explicit?: number): number | undefined {
  if (typeof explicit === 'number') return explicit
  const status = asRecord(error)?.response?.status
  return typeof status === 'number' ? status : undefined
}

function readCode(error: unknown, explicit?: string): string {
  if (explicit) return explicit
  const rec = asRecord(error)
  if (typeof rec?.code === 'string') return rec.code
  if (typeof rec?.error === 'string') return rec.error
  return ''
}

function readJsonDetail(text: string): string {
  const trimmed = text.trim()
  if (!trimmed.startsWith('{')) return ''
  try {
    const parsed = JSON.parse(trimmed) as unknown
    if (!parsed || typeof parsed !== 'object') return ''
    const detail = (parsed as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
    if (detail && typeof detail === 'object') {
      const nested = detail as { code?: unknown; message?: unknown }
      return [nested.code, nested.message].filter((part) => typeof part === 'string').join(' ')
    }
    const message = (parsed as { message?: unknown }).message
    return typeof message === 'string' ? message : ''
  } catch {
    return ''
  }
}

function collectErrorText(error: unknown): string {
  const parts: string[] = []
  if (typeof error === 'string') {
    parts.push(error, readJsonDetail(error))
  }
  if (error instanceof Error) {
    parts.push(error.message, readJsonDetail(error.message))
  }
  const rec = asRecord(error)
  if (typeof rec?.message === 'string') parts.push(rec.message, readJsonDetail(rec.message))
  if (typeof rec?.error === 'string') parts.push(rec.error)
  if (typeof rec?.code === 'string') parts.push(rec.code)
  if (typeof rec?.detail === 'string') parts.push(rec.detail)
  return parts.filter(Boolean).join(' ').toLowerCase()
}

/**
 * Expected-recoverable visitor-session failures: HTTP 401 and socket
 * auth rejects. HTTP remint requires status 401 — body copy alone is
 * not enough. HTTP 5xx is never remint-recoverable even when the body
 * mentions 401. join_conversation NOT_FOUND is handled separately.
 */
export function isRecoverableVisitorSessionError(
  error: unknown,
  options?: {
    context?: VisitorRecoverableErrorContext
    status?: number
    code?: string
  },
): boolean {
  if (error == null || error === '') return false

  const status = readHttpStatus(error, options?.status)
  if (typeof status === 'number' && status >= 500) return false
  if (status === 401) return true
  // HTTP remint is 401-only. A 422 mentioning visitor_session_token is a
  // validation error and must not burn the remint budget.
  if (options?.context === 'http') return false

  const code = readCode(error, options?.code)
  if ((RECOVERABLE_VISITOR_SESSION_CODES as readonly string[]).includes(code)) return true

  const text = collectErrorText(error)
  return RECOVERABLE_MESSAGE_FRAGMENTS.some((fragment) => text.includes(fragment))
}

export function visitorRecoveryTelemetryLevel(input: {
  recoverable: boolean
  recoveryExhausted?: boolean
}): TelemetryLevel {
  if (input.recoverable && !input.recoveryExhausted) return 'warn'
  return 'error'
}
