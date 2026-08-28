import { describe, expect, it } from 'vitest'
import {
  abandonRateLimitApiToFormPercent,
  abandonRateLimitFormToApi,
  importResultToastParams,
  isAbandonOverLimit,
  toFiniteNumber,
} from '@/lib/auto-outbound-numbers'

describe('toFiniteNumber', () => {
  it('coerces decimal strings from the API', () => {
    expect(toFiniteNumber('0.03')).toBe(0.03)
    expect(toFiniteNumber('1.5')).toBe(1.5)
    expect(toFiniteNumber(null)).toBeNull()
    expect(toFiniteNumber('')).toBeNull()
    expect(toFiniteNumber('x')).toBeNull()
  })
})

describe('abandon_rate_limit unit conversion', () => {
  it('converts API decimal to form percent for display', () => {
    expect(abandonRateLimitApiToFormPercent('0.03')).toBeCloseTo(3)
    expect(abandonRateLimitApiToFormPercent(0.05)).toBeCloseTo(5)
    expect(abandonRateLimitApiToFormPercent(null)).toBe(3)
  })

  it('converts form percent to API decimal on submit', () => {
    expect(abandonRateLimitFormToApi(3)).toBeCloseTo(0.03)
    expect(abandonRateLimitFormToApi('5')).toBeCloseTo(0.05)
    expect(abandonRateLimitFormToApi(null)).toBeNull()
  })
})

describe('isAbandonOverLimit', () => {
  it('compares rate and limit in the same 0–1 unit', () => {
    expect(isAbandonOverLimit(0.04, 0.03)).toBe(true)
    expect(isAbandonOverLimit('0.02', '0.03')).toBe(false)
    expect(isAbandonOverLimit(0.03, 0.03)).toBe(false)
    expect(isAbandonOverLimit(null, 0.03)).toBe(false)
    expect(isAbandonOverLimit(0.04, null)).toBe(false)
  })
})

describe('importResultToastParams', () => {
  it('maps import response fields to toast params', () => {
    expect(
      importResultToastParams({
        created: 10,
        failed: 2,
        skipped_rate_limited: 3,
      }),
    ).toEqual({ created: 10, failed: 2, skipped: 3 })
  })
})
