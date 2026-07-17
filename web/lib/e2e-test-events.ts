/**
 * Test-only event channel for embedded chat pages.
 * Enabled when the chat URL includes opendesk_test=1 (set by the SDK in testMode).
 */

let enabled = false
let instanceId: string | null = null

export function initTestEventChannel(): void {
  if (typeof window === 'undefined') return
  const params = new URLSearchParams(window.location.search)
  if (params.get('opendesk_test') !== '1') return
  enabled = true
  instanceId = params.get('opendesk_instance')
}

export function emitTestEvent(
  event: string,
  payload: Record<string, unknown> = {},
): void {
  if (!enabled || typeof window === 'undefined' || !instanceId) return
  if (window.parent === window) return
  window.parent.postMessage(
    {
      source: 'opendesk-chat',
      type: 'test-event',
      instanceId,
      event,
      payload,
    },
    '*',
  )
}
