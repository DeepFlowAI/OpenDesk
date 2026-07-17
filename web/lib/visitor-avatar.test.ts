import { describe, expect, it } from 'vitest'

import { resolveVisitorAvatarState, visitorAvatarInitial } from './visitor-avatar'

describe('visitor avatar presentation', () => {
  it('normalizes the visitor initial', () => {
    expect(visitorAvatarInitial('  alice')).toBe('A')
    expect(visitorAvatarInitial(' 张三')).toBe('张')
    expect(visitorAvatarInitial('')).toBe('访')
    expect(visitorAvatarInitial(null)).toBe('访')
  })

  it('uses confirmed online and offline states', () => {
    expect(resolveVisitorAvatarState({ enabled: true, status: 'online' })).toBe('online')
    expect(resolveVisitorAvatarState({ enabled: true, status: 'offline' })).toBe('offline')
  })

  it('falls back to unknown when status cannot be confirmed', () => {
    expect(resolveVisitorAvatarState({ enabled: false, status: 'online' })).toBe('unknown')
    expect(resolveVisitorAvatarState({ enabled: true, status: 'online', canDisplay: false })).toBe('unknown')
    expect(resolveVisitorAvatarState({ enabled: true, status: 'online', isError: true })).toBe('unknown')
    expect(resolveVisitorAvatarState({ enabled: true })).toBe('unknown')
  })
})
