import { describe, expect, it } from 'vitest'

import { isCrawlerUserAgent, isIgnorableClientError } from './client-error-filters'

describe('isCrawlerUserAgent', () => {
  it('skips known crawlers and keeps real browsers', () => {
    expect(isCrawlerUserAgent('meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)')).toBe(true)
    expect(isCrawlerUserAgent('facebookexternalhit/1.1')).toBe(true)
    expect(
      isCrawlerUserAgent(
        'Mozilla/5.0 (iPhone; CPU iPhone OS 16_3_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148',
      ),
    ).toBe(false)
  })
})

describe('isIgnorableClientError', () => {
  it('ignores ResizeObserver browser noise', () => {
    expect(isIgnorableClientError('ResizeObserver loop completed with undelivered notifications.')).toBe(true)
    expect(isIgnorableClientError(new Error('ResizeObserver loop limit exceeded'))).toBe(true)
  })

  it('ignores best-effort embed control release 401s', () => {
    expect(
      isIgnorableClientError(
        new Error('Request failed with status code 401 Unauthorized: POST https://opendesk.example/api/v1/call-center/embed/control/release'),
      ),
    ).toBe(true)
    expect(
      isIgnorableClientError({
        message: 'Request failed with status code 401 Unauthorized',
        request: { url: 'https://opendesk.example/api/v1/call-center/embed/control/release' },
        response: { status: 401 },
      }),
    ).toBe(true)
  })

  it('keeps real client failures', () => {
    expect(isIgnorableClientError(new TypeError('Cannot read properties of undefined'))).toBe(false)
    expect(
      isIgnorableClientError({
        message: 'Request failed with status code 500 Internal Server Error',
        request: { url: 'https://opendesk.example/api/v1/call-center/embed/control/release' },
        response: { status: 500 },
      }),
    ).toBe(false)
  })
})
