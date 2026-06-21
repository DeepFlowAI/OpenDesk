import type { TelemetryLevel } from '@/models/telemetry'
import { telemetry } from '@/service/telemetry'

type AuthLogDetail = Record<string, string | number | boolean | undefined>

const AUTH_TELEMETRY_EVENTS: Record<string, { name: string; level: TelemetryLevel }> = {
  token_refresh_succeeded: { name: 'auth_token_refresh_succeeded', level: 'info' },
  token_refresh_failed: { name: 'auth_token_refresh_failed', level: 'warn' },
  session_cleared: { name: 'auth_session_cleared', level: 'warn' },
  api_unauthorized: { name: 'auth_api_unauthorized', level: 'warn' },
  socket_auth_failed: { name: 'auth_socket_auth_failed', level: 'warn' },
}

function toTelemetryProps(detail?: AuthLogDetail): Record<string, string | number | boolean> | null {
  if (!detail) return null
  const props: Record<string, string | number | boolean> = {}
  for (const [key, value] of Object.entries(detail)) {
    if (value === undefined) continue
    const normalizedKey = key.replace(/[A-Z]/g, (char) => `_${char.toLowerCase()}`)
    props[normalizedKey] = value
  }
  return Object.keys(props).length > 0 ? props : null
}

/** Client-side auth lifecycle events (session refresh, forced logout). */
export async function logAuthEvent(
  event: string,
  detail?: AuthLogDetail,
  options?: { immediate?: boolean },
): Promise<void> {
  if (detail && Object.keys(detail).length > 0) {
    console.warn(`[auth] ${event}`, detail)
  } else {
    console.warn(`[auth] ${event}`)
  }

  const mapped = AUTH_TELEMETRY_EVENTS[event] ?? {
    name: `auth_${event.replace(/[^a-z0-9_]/g, '_')}`,
    level: 'warn' as TelemetryLevel,
  }
  telemetry.trackApp(mapped.name, {
    level: mapped.level,
    props: toTelemetryProps(detail),
  })
  if (options?.immediate) {
    await telemetry.flushApp()
  }
}
