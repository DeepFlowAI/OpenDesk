const RELOAD_MARKER_KEY = 'opendesk:chunk-error-reloaded-at'
const RELOAD_COOLDOWN_MS = 10_000

export function isChunkLoadError(reason: unknown): boolean {
  if (!reason) return false
  const name = (reason as { name?: string }).name
  const message = (reason as { message?: string }).message ?? String(reason)
  return name === 'ChunkLoadError' || /Loading (CSS )?chunk [\w-]+ failed/i.test(message)
}

export function reloadOnceOnChunkError(): boolean {
  try {
    const last = Number(sessionStorage.getItem(RELOAD_MARKER_KEY) ?? 0)
    if (Date.now() - last < RELOAD_COOLDOWN_MS) return false
    sessionStorage.setItem(RELOAD_MARKER_KEY, String(Date.now()))
  } catch {
    // sessionStorage unavailable: still try a single reload.
  }
  window.location.reload()
  return true
}
