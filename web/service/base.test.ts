import { describe, expect, it } from 'vitest'

import { normalizeApiBase } from '@/service/base'

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
