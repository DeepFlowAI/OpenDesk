'use client'

import { useEffect } from 'react'

import { isChunkLoadError, reloadOnceOnChunkError } from '@/lib/chunk-load-error'

/**
 * Globally recovers from webpack ChunkLoadError by reloading once. Mounted at
 * the root so it covers every route. Renders nothing.
 */
export function ChunkErrorReloader() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      if (isChunkLoadError(event.error)) reloadOnceOnChunkError()
    }
    const onRejection = (event: PromiseRejectionEvent) => {
      if (isChunkLoadError(event.reason)) reloadOnceOnChunkError()
    }
    window.addEventListener('error', onError)
    window.addEventListener('unhandledrejection', onRejection)
    return () => {
      window.removeEventListener('error', onError)
      window.removeEventListener('unhandledrejection', onRejection)
    }
  }, [])

  return null
}
