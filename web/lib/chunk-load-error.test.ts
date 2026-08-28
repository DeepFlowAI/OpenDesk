import { afterEach, describe, expect, it, vi } from 'vitest'

import { isChunkLoadError, reloadOnceOnChunkError } from './chunk-load-error'

describe('isChunkLoadError', () => {
  it('matches webpack chunk failures', () => {
    expect(isChunkLoadError({ name: 'ChunkLoadError', message: 'Loading chunk 7177 failed.' })).toBe(true)
    expect(isChunkLoadError(new Error('Loading CSS chunk 12 failed'))).toBe(true)
    expect(isChunkLoadError(new Error('boom'))).toBe(false)
  })
})

describe('reloadOnceOnChunkError', () => {
  afterEach(() => {
    sessionStorage.clear()
    vi.unstubAllGlobals()
  })

  it('reloads once and then cools down', () => {
    const reload = vi.fn()
    vi.stubGlobal('location', { reload })

    expect(reloadOnceOnChunkError()).toBe(true)
    expect(reload).toHaveBeenCalledTimes(1)
    expect(reloadOnceOnChunkError()).toBe(false)
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
