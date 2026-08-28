export type VisitorCredential = {
  visitorExternalId: string
  visitorSecret: string
  visitorSessionToken?: string
  visitorSessionExpiresAt?: number
  visitorPayloadKey?: string
}

export type VisitorInitSource = 'sdk' | 'timeout' | 'standalone'

export type VisitorIdentityPayload = {
  visitor?: unknown
  /**
   * `undefined` — host did not provide a token (safe to reuse stored identity).
   * `null` — host explicitly cleared identity (logout; do not reuse).
   * `string` — active context token.
   */
  contextToken?: string | null
  initSource?: VisitorInitSource
}

export type VisitorIdentitySource = 'stored' | 'context' | 'fresh'

/**
 * Stable key for the identity claims that minted a visitor credential.
 * Used to detect intentional account switches (different contextToken).
 */
export function getVisitorPayloadKey(payload?: VisitorIdentityPayload | null): string {
  return JSON.stringify({
    visitor: payload?.visitor || null,
    contextToken: payload?.contextToken || null,
  })
}

/**
 * Decide whether localStorage credentials can be renewed for the current payload.
 *
 * - Same payload key → reuse.
 * - `contextToken === null` → explicit logout; do not reuse.
 * - `contextToken` absent (`undefined`) → reuse last proven identity (refresh / SDK race).
 * - Different non-null `contextToken` → do not reuse; mint from the new context.
 */
export function selectStoredVisitorCredential(
  stored: VisitorCredential | null | undefined,
  currentPayload: VisitorIdentityPayload,
): VisitorCredential | null {
  if (!stored?.visitorExternalId || !stored.visitorSecret) return null
  if (currentPayload.contextToken === null) return null
  const currentKey = getVisitorPayloadKey(currentPayload)
  if (stored.visitorPayloadKey === currentKey) return stored
  if (currentPayload.contextToken === undefined) return stored
  return null
}

/**
 * Fold an SDK `init`/`open` into the current payload.
 *
 * The first identity-bearing payload wins, but an empty fallback must not lock
 * out a later init that does carry identity. Anything that changes nothing
 * returns the current object unchanged, so re-opening the widget does not look
 * like a new payload and re-mint the visitor session.
 */
export function mergeEmbedInitPayload<T extends VisitorIdentityPayload>(
  current: T | null | undefined,
  incoming: T,
): T {
  if (!current) return incoming
  if (current.contextToken || current.visitor) return current
  if (incoming.contextToken || incoming.visitor) return incoming
  // No identity either way: only accept the SDK answering a timeout fallback,
  // which releases the auto-start hold.
  if (current.initSource === 'timeout' && incoming.initSource === 'sdk') return incoming
  return current
}

/**
 * The identity-less timeout fallback holds off on starting a conversation, so a
 * late SDK init carrying contextToken does not end up creating a second session.
 * Once the grace period is over it starts anyway — a host page with a stale SDK
 * may never send `init`, and the visitor still needs a usable chat.
 */
export function shouldAutoStartConversation(
  payload: VisitorIdentityPayload,
  graceElapsed: boolean,
): boolean {
  if (payload.initSource !== 'timeout') return true
  return graceElapsed
}

export function resolveVisitorIdentitySource(input: {
  reused: boolean
  hadStoredCredential: boolean
  hasContextToken: boolean
}): VisitorIdentitySource {
  if (input.reused || (input.hadStoredCredential && !input.hasContextToken)) return 'stored'
  if (input.hasContextToken) return 'context'
  return 'fresh'
}
