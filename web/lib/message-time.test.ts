import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { formatMessageTime } from './message-time'

describe('formatMessageTime', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 7, 18, 15, 30, 45))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows clock only for today', () => {
    expect(formatMessageTime(new Date(2026, 7, 18, 11, 25, 58), 'zh')).toBe('11:25')
    expect(formatMessageTime(new Date(2026, 7, 18, 11, 25, 58), 'zh', { seconds: true })).toBe(
      '11:25:58',
    )
  })

  it('keeps yesterday with localized prefix', () => {
    const yesterday = new Date(2026, 7, 17, 9, 8, 7)
    expect(formatMessageTime(yesterday, 'zh')).toBe('昨天 09:08')
    expect(formatMessageTime(yesterday, 'en')).toBe('Yesterday 09:08')
    expect(formatMessageTime(yesterday, 'zh', { seconds: true })).toBe('昨天 09:08:07')
  })

  it('adds month and day for earlier dates in the same year', () => {
    expect(formatMessageTime(new Date(2026, 2, 5, 9, 8, 0), 'zh')).toBe('03-05 09:08')
  })

  it('adds year for dates outside the current year', () => {
    expect(formatMessageTime(new Date(2025, 11, 31, 23, 59, 1), 'zh')).toBe('2025-12-31 23:59')
    expect(formatMessageTime(new Date(2025, 11, 31, 23, 59, 1), 'zh', { seconds: true })).toBe(
      '2025-12-31 23:59:01',
    )
  })

  it('treats the previous calendar day as yesterday across month boundaries', () => {
    vi.setSystemTime(new Date(2026, 7, 1, 10, 0, 0))
    expect(formatMessageTime(new Date(2026, 6, 31, 22, 15, 0), 'zh')).toBe('昨天 22:15')
  })

  it('returns empty string for invalid input', () => {
    expect(formatMessageTime('not-a-date', 'zh')).toBe('')
  })
})
