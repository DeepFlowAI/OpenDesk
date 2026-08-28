import type { TelemetryLevel } from '@/models/telemetry'
import { useAuthStore } from '@/context/auth-store'
import { telemetry } from '@/service/telemetry'

type AuthLogDetail = Record<string, string | number | boolean | undefined>

const AUTH_TELEMETRY_EVENTS: Record<string, { name: string; level: TelemetryLevel }> = {
  token_refresh_succeeded: { name: 'auth_token_refresh_succeeded', level: 'info' },
  token_refresh_failed: { name: 'auth_token_refresh_failed', level: 'warn' },
  session_cleared: { name: 'auth_session_cleared', level: 'warn' },
  session_clear_skipped: { name: 'auth_session_clear_skipped', level: 'warn' },
  api_unauthorized: { name: 'auth_api_unauthorized', level: 'warn' },
  socket_auth_failed: { name: 'auth_socket_auth_failed', level: 'warn' },
  token_adopted_from_storage: { name: 'auth_token_adopted_from_storage', level: 'info' },
  /** Login page rendered a forced-logout banner from ?reason=. */
  login_notice_shown: { name: 'auth_login_notice_shown', level: 'info' },
  /** Another tab signed in a different account; this tab reloaded onto it. */
  account_switched: { name: 'auth_account_switched', level: 'warn' },
  /** Kept a signing-in tab alive instead of reloading it onto another account. */
  account_switch_reload_skipped: { name: 'auth_account_switch_reload_skipped', level: 'info' },
}

/** Stable per-tab id so concurrent tabs for the same device can be told apart. */
const TAB_ID =
  typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10)

function readIdentityProps(): { user_id?: number; tenant_id?: number } {
  try {
    const user = useAuthStore.getState().user
    if (user) {
      return { user_id: user.id, tenant_id: user.tenant_id }
    }
  } catch {
    // fall through to persisted store
  }

  try {
    if (typeof localStorage === 'undefined') return {}
    const raw = localStorage.getItem('app-auth')
    if (!raw) return {}
    const parsed = JSON.parse(raw) as {
      state?: { user?: { id?: unknown; tenant_id?: unknown } | null }
    }
    const persisted = parsed.state?.user
    if (!persisted) return {}
    const userId = typeof persisted.id === 'number' ? persisted.id : undefined
    const tenantId = typeof persisted.tenant_id === 'number' ? persisted.tenant_id : undefined
    return {
      ...(userId !== undefined ? { user_id: userId } : {}),
      ...(tenantId !== undefined ? { tenant_id: tenantId } : {}),
    }
  } catch {
    return {}
  }
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
  options?: { immediate?: boolean; level?: TelemetryLevel },
): Promise<void> {
  const identity = readIdentityProps()
  const page =
    typeof window !== 'undefined'
      ? {
          pathname: window.location.pathname,
          search: window.location.search || undefined,
        }
      : {}
  const enriched: AuthLogDetail = {
    ...detail,
    ...identity,
    tab_id: TAB_ID,
    ...page,
    ...(typeof document !== 'undefined' ? { visibility: document.visibilityState } : {}),
  }

  console.warn(`[auth] ${event}`, enriched)

  const mapped = AUTH_TELEMETRY_EVENTS[event] ?? {
    name: `auth_${event.replace(/[^a-z0-9_]/g, '_')}`,
    level: 'warn' as TelemetryLevel,
  }
  telemetry.trackApp(mapped.name, {
    level: options?.level ?? mapped.level,
    props: toTelemetryProps(enriched),
  })
  if (options?.immediate) {
    await telemetry.flushApp()
  }
}
