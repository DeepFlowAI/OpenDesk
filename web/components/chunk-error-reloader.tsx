'use client'

import { useEffect } from 'react'

// When a new version is deployed, the HTML a user already has open can
// reference JS/CSS chunks whose hashed filenames no longer exist; a corrupted
// browser disk cache can likewise fail to read an otherwise-valid chunk. Both
// surface as a webpack "ChunkLoadError" and break client-side navigation.
// We recover by forcing a single hard reload, which fetches fresh HTML +
// chunks. A short cooldown in sessionStorage prevents an infinite reload loop
// when a reload does not fix the problem (e.g. a genuinely missing file).
const RELOAD_MARKER_KEY = 'opendesk:chunk-error-reloaded-at'
const RELOAD_COOLDOWN_MS = 10_000

function isChunkLoadError(reason: unknown): boolean {
  if (!reason) return false
  const name = (reason as { name?: string }).name
  const message = (reason as { message?: string }).message ?? String(reason)
  return name === 'ChunkLoadError' || /Loading (CSS )?chunk [\w-]+ failed/i.test(message)
}

function reloadOnce() {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_MARKER_KEY) ?? 0)
    if (Date.now() - last < RELOAD_COOLDOWN_MS) return
    sessionStorage.setItem(RELOAD_MARKER_KEY, String(Date.now()))
  } catch {
    // sessionStorage unavailable (private mode quirks): reload anyway.
  }
  window.location.reload()
}

/**
 * Globally recovers from webpack ChunkLoadError by reloading once. Mounted at
 * the root so it covers every route. Renders nothing.
 */
export function ChunkErrorReloader() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      if (isChunkLoadError(event.error)) reloadOnce()
    }
    const onRejection = (event: PromiseRejectionEvent) => {
      if (isChunkLoadError(event.reason)) reloadOnce()
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
