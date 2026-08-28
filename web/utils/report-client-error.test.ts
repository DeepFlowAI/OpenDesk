import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const trackApp = vi.fn()
const flushApp = vi.fn()

vi.mock('@/service/telemetry', () => ({
  telemetry: {
    trackApp: (...args: unknown[]) => trackApp(...args),
    flushApp: (...args: unknown[]) => flushApp(...args),
  },
}))

import { reportClientError } from '@/utils/report-client-error'

describe('reportClientError', () => {
  beforeEach(() => {
    trackApp.mockReset()
    flushApp.mockReset()
    flushApp.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('does not report crawler crashes', async () => {
    vi.stubGlobal('navigator', { userAgent: 'meta-externalagent/1.1 (+https://developers.facebook.com/docs/sharing/webmasters/crawler)' })

    await reportClientError('app_render_crashed', new Error('Loading chunk 7177 failed.'))

    expect(trackApp).not.toHaveBeenCalled()
  })

  it('reports leftover chunk failures as warnings', async () => {
    vi.stubGlobal('navigator', {
      userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_3_1 like Mac OS X) AppleWebKit/605.1.15',
    })

    const error = new Error('Loading chunk 9282 failed.')
    error.name = 'ChunkLoadError'
    await reportClientError('app_render_crashed', error)

    expect(trackApp).toHaveBeenCalledWith(
      'app_render_crashed',
      expect.objectContaining({
        level: 'warn',
        props: expect.objectContaining({
          error_name: 'ChunkLoadError',
        }),
      }),
    )
  })

  it('does not report ignorable browser and cleanup noise', async () => {
    vi.stubGlobal('navigator', {
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    })

    await reportClientError(
      'app_unhandled_error',
      'ResizeObserver loop completed with undelivered notifications.',
    )
    await reportClientError(
      'app_unhandled_rejection',
      new Error('Request failed with status code 401 Unauthorized: POST https://opendesk.example/api/v1/call-center/embed/control/release'),
    )

    expect(trackApp).not.toHaveBeenCalled()
  })

  it('still reports real unhandled failures as errors', async () => {
    vi.stubGlobal('navigator', {
      userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    })

    await reportClientError('app_unhandled_rejection', new TypeError('Cannot read properties of undefined'))

    expect(trackApp).toHaveBeenCalledWith(
      'app_unhandled_rejection',
      expect.objectContaining({
        level: 'error',
        props: expect.objectContaining({
          error_name: 'TypeError',
        }),
      }),
    )
  })
})
