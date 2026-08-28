import { describe, expect, it } from 'vitest'

import { isCredentialChallengeUrl, normalizeApiBase } from '@/service/base'

describe('normalizeApiBase', () => {
  it('strips a single trailing slash so refresh URLs have no double slash', () => {
    const base = normalizeApiBase('https://opendesk.example.com/api/')
    expect(`${base}/v1/auth/refresh`).toBe('https://opendesk.example.com/api/v1/auth/refresh')
  })

  it('strips multiple trailing slashes', () => {
    const base = normalizeApiBase('https://opendesk.example.com/api///')
    expect(`${base}/v1/auth/refresh`).toBe('https://opendesk.example.com/api/v1/auth/refresh')
  })

  it('leaves a base without trailing slash unchanged', () => {
    const base = normalizeApiBase('https://opendesk.example.com/api')
    expect(`${base}/v1/auth/refresh`).toBe('https://opendesk.example.com/api/v1/auth/refresh')
  })

  it('treats empty / undefined as an empty base', () => {
    expect(normalizeApiBase('')).toBe('')
    expect(normalizeApiBase(undefined)).toBe('')
    expect(`${normalizeApiBase('')}/v1/auth/refresh`).toBe('/v1/auth/refresh')
  })
})

describe('isCredentialChallengeUrl', () => {
  it('matches login / sso / password-reset auth endpoints', () => {
    expect(isCredentialChallengeUrl('https://x/api/v1/auth/login')).toBe(true)
    expect(isCredentialChallengeUrl('https://x/api/v1/auth/sso')).toBe(true)
    expect(isCredentialChallengeUrl('https://x/api/v1/auth/send-verify-code')).toBe(true)
    expect(isCredentialChallengeUrl('https://x/api/v1/auth/reset-password')).toBe(true)
  })

  it('does not match session endpoints that should clear auth on 401', () => {
    expect(isCredentialChallengeUrl('https://x/api/v1/auth/refresh')).toBe(false)
    expect(isCredentialChallengeUrl('https://x/api/v1/auth/me')).toBe(false)
    expect(isCredentialChallengeUrl('https://x/api/v1/tickets')).toBe(false)
  })
})
