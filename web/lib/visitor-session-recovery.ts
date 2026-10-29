import { isRecoverableVisitorSessionError } from '@/lib/visitor-session-recoverable-error'

export const MAX_SESSION_RECOVERIES = 3
export const MAX_JOIN_NOT_FOUND_REPLACES_PER_CONNECTION = 2
export const SESSION_RECOVERY_BUDGET_DECAY_MS = 10 * 60 * 1000
export const VISITOR_SESSION_RECOVERY_EXHAUSTED_EVENT = 'visitor_session_recovery_exhausted'
export const CONVERSATION_SUBSCRIPTION_REPLACED_EVENT = 'conversation_subscription_replaced'

export type SessionRecoveryBudget = {
  token: string | null
  attempts: number
  lastAttemptAt: number | null
}

export type VisitorSessionRecoveryFailure = 'budget_exhausted' | 'mint_failed'

export type RecoverVisitorSessionOptions = {
  reconnectSocket?: boolean
}

export type SessionRecoveryFlightState = {
  wantReconnect: boolean
  didReconnect: boolean
  visitorExternalId: string | null
  generation: number
}

export type JoinNotFoundReplaceOptions = {
  ended?: boolean
  replaceCount?: number
  maxReplaces?: number
}

export type JoinNotFoundReplaceTelemetry = {
  name: typeof CONVERSATION_SUBSCRIPTION_REPLACED_EVENT
  level: 'warn'
  conversation_external_id: string
  props: {
    error: 'NOT_FOUND'
    replaced: true
  }
}

export type JoinNotFoundReplaceDecision =
  | {
      action: 'replace'
      discardedId: string
      replaceCount: number
      telemetry: JoinNotFoundReplaceTelemetry
    }
  | {
      action: 'fail'
      discardedId: string
      replaceAttempted: boolean
    }

/** Upgrade an in-flight remint so a later reconnectSocket caller is not dropped. */
export function requestSessionRecoveryReconnect(flight: SessionRecoveryFlightState): void {
  flight.wantReconnect = true
}

/**
 * Claim the single post-remint reconnect. Concurrent waiters must not
 * disconnect/connect the socket twice. Returns the visitor id to reconnect
 * with, or null when this flight should not reconnect.
 */
export function claimSessionRecoveryReconnect(
  flight: SessionRecoveryFlightState,
): string | null {
  if (!flight.wantReconnect || flight.didReconnect || !flight.visitorExternalId) {
    return null
  }
  flight.didReconnect = true
  return flight.visitorExternalId
}

/** A remint that outlives a later init/login/logout must not write back. */
export function isSessionRecoveryFlightCurrent(
  flightGeneration: number,
  currentGeneration: number,
): boolean {
  return flightGeneration === currentGeneration
}

/**
 * Reminting to a different visitor id leaves the existing socket bound to
 * the previous identity. applySessionToken only updates socket.auth for the
 * next handshake, so the next join/HTTP mix would 404.
 */
export function shouldForceSessionRecoveryReconnect(
  previousVisitorExternalId: string | null,
  nextVisitorExternalId: string,
): boolean {
  return (
    previousVisitorExternalId != null
    && previousVisitorExternalId !== nextVisitorExternalId
  )
}

/**
 * Claim the post-remint reconnect. An identity change always reconnects,
 * even when the caller only asked to refresh HTTP auth.
 */
export function resolveSessionRecoveryReconnectIntent(
  flight: SessionRecoveryFlightState,
  previousVisitorExternalId: string | null,
  nextVisitorExternalId: string,
): string | null {
  flight.visitorExternalId = nextVisitorExternalId
  if (shouldForceSessionRecoveryReconnect(previousVisitorExternalId, nextVisitorExternalId)) {
    requestSessionRecoveryReconnect(flight)
  }
  return claimSessionRecoveryReconnect(flight)
}

/** mint_failed on a still-usable budget is a retryable warn, not an alarm. */
export function sessionRecoveryFailureTelemetryLevel(
  reason: VisitorSessionRecoveryFailure,
  attempts: number,
): 'warn' | 'error' {
  if (reason === 'mint_failed' && canAttemptSessionRecovery(attempts)) {
    return 'warn'
  }
  return 'error'
}

export function emptySessionRecoveryBudget(): SessionRecoveryBudget {
  return { token: null, attempts: 0, lastAttemptAt: null }
}

export function canAttemptSessionRecovery(attempts: number): boolean {
  return attempts < MAX_SESSION_RECOVERIES
}

export function isSessionRecoveryBudgetDecayed(
  budget: SessionRecoveryBudget,
  now: number,
): boolean {
  if (budget.lastAttemptAt == null || budget.attempts === 0) return false
  return now - budget.lastAttemptAt >= SESSION_RECOVERY_BUDGET_DECAY_MS
}

/**
 * Remint budget is keyed by the token it is following. A later expiry of
 * a different token can recover again; a remint chain must call
 * followSessionRecoveryToken so the count is not reset. After the decay
 * window the count is spent and a later expiry can remint again.
 */
export function canAttemptSessionRecoveryForToken(
  budget: SessionRecoveryBudget,
  token: string | null,
  now: number = Date.now(),
): boolean {
  if (isSessionRecoveryBudgetDecayed(budget, now)) return true
  if (budget.token !== token) return true
  return canAttemptSessionRecovery(budget.attempts)
}

export function recordSessionRecoveryAttempt(
  budget: SessionRecoveryBudget,
  token: string | null,
  now: number = Date.now(),
): SessionRecoveryBudget {
  if (isSessionRecoveryBudgetDecayed(budget, now) || budget.token !== token) {
    return { token, attempts: 1, lastAttemptAt: now }
  }
  return { token: budget.token, attempts: budget.attempts + 1, lastAttemptAt: now }
}

/**
 * Keep the remint count when minting a replacement token so join/connect
 * success cannot reset a chain the remint itself just triggered. The decay
 * clock stays on lastAttemptAt.
 */
export function followSessionRecoveryToken(
  budget: SessionRecoveryBudget,
  nextToken: string,
): SessionRecoveryBudget {
  return {
    token: nextToken,
    attempts: budget.attempts,
    lastAttemptAt: budget.lastAttemptAt,
  }
}

/**
 * join_conversation NOT_FOUND means the conversation public id is no longer
 * valid for the current identity. Re-emitting join or re-handshaking cannot
 * recover. Discard the id so start_conversation can mint or resume — but an
 * already-ended conversation must not self-heal into a new queued session,
 * and each socket connection may replace only a few times.
 */
export function decideJoinNotFoundReplace(
  discardedId: string | null,
  conversationId: string,
  options?: JoinNotFoundReplaceOptions,
): JoinNotFoundReplaceDecision {
  const ended = options?.ended === true
  const replaceCount = options?.replaceCount ?? 0
  const maxReplaces = options?.maxReplaces ?? MAX_JOIN_NOT_FOUND_REPLACES_PER_CONNECTION

  if (ended) {
    return {
      action: 'fail',
      discardedId: discardedId ?? conversationId,
      replaceAttempted: replaceCount > 0,
    }
  }
  if (replaceCount >= maxReplaces) {
    return {
      action: 'fail',
      discardedId: discardedId ?? conversationId,
      replaceAttempted: true,
    }
  }
  if (discardedId === conversationId) {
    return { action: 'fail', discardedId, replaceAttempted: true }
  }
  return {
    action: 'replace',
    discardedId: conversationId,
    replaceCount: replaceCount + 1,
    telemetry: {
      name: CONVERSATION_SUBSCRIPTION_REPLACED_EVENT,
      level: 'warn',
      conversation_external_id: conversationId,
      props: { error: 'NOT_FOUND', replaced: true },
    },
  }
}

/**
 * Dedup exhausted/mint-failed telemetry by token. Use `undefined` as the
 * unreported sentinel so a null token can still emit once.
 */
export function shouldReportSessionRecoveryExhausted(
  reportedToken: string | null | undefined,
  activeToken: string | null,
): boolean {
  return reportedToken !== activeToken
}

/**
 * Retry a visitor-token HTTP call after minting a fresh session.
 * Non-recoverable errors and a failed/exhausted remint rethrow the original error.
 */
export async function withVisitorSessionRecovery<T>(
  run: (visitorSessionToken: string) => Promise<T>,
  options: {
    visitorSessionToken: string
    recoverVisitorSession: () => Promise<string | null>
  },
): Promise<T> {
  try {
    return await run(options.visitorSessionToken)
  } catch (error) {
    if (!isRecoverableVisitorSessionError(error, { context: 'http' })) {
      throw error
    }
    const token = await options.recoverVisitorSession()
    if (!token) throw error
    return run(token)
  }
}
