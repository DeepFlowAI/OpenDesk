/**
 * Numeric helpers for auto-outbound API decimals (often serialized as strings).
 */

export function toFiniteNumber(value: number | string | null | undefined): number | null {
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

/**
 * Form UI uses abandon_rate_limit as percent 0–100.
 * API / DB store a 0–1 decimal (e.g. "0.03").
 */
export function abandonRateLimitApiToFormPercent(
  apiValue: number | string | null | undefined,
  fallback = 3,
): number {
  const n = toFiniteNumber(apiValue)
  if (n == null) return fallback
  return n * 100
}

/** Convert form percent (0–100) to API decimal (0–1). */
export function abandonRateLimitFormToApi(
  formPercent: number | string | null | undefined,
): number | null {
  const n = toFiniteNumber(formPercent)
  if (n == null) return null
  return n / 100
}

/** Compare abandon_rate and abandon_rate_limit in the same 0–1 unit. */
export function isAbandonOverLimit(
  abandonRate: number | string | null | undefined,
  abandonRateLimit: number | string | null | undefined,
): boolean {
  const rate = toFiniteNumber(abandonRate)
  const limit = toFiniteNumber(abandonRateLimit)
  if (rate == null || limit == null) return false
  return rate > limit
}

export type AutoOutboundImportToastParams = {
  created: number
  failed: number
  skipped: number
}

/** Map import API response fields to toast i18n params. */
export function importResultToastParams(result: {
  created: number
  failed: number
  skipped_rate_limited: number
}): AutoOutboundImportToastParams {
  return {
    created: result.created,
    failed: result.failed,
    skipped: result.skipped_rate_limited,
  }
}
