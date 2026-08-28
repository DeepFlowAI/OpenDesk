'use client'

import { useEffect } from 'react'
import { useSocketStore } from '@/context/socket-store'

/**
 * Owns the workspace Socket.IO connection.
 *
 * A single connection serves both the online-chat and the call-center surface,
 * so exactly one place may decide when to open it. When more than one place
 * decides, their conditions drift apart and an agent can end up unreachable on
 * one surface while everything looks healthy on the other.
 */
export function useWorkspaceSocket(enabled: boolean, token: string | null): void {
  const { socket, connected, connecting, authFailed, connect } = useSocketStore()

  useEffect(() => {
    if (enabled && token && !connected && !connecting && !authFailed) {
      connect(token)
    }
    // `socket` is a dependency so that dropping a dead instance re-runs this
    // and rebuilds the connection.
  }, [enabled, token, socket, connected, connecting, authFailed, connect])

  // A backgrounded tab may be frozen by the browser and its socket dies without
  // notice. Re-check on the way back so the agent becomes reachable in the same
  // frame instead of waiting for the next reconnection tick.
  useEffect(() => {
    if (!enabled) return

    const handleVisibilityChange = () => {
      if (document.visibilityState !== 'visible') return
      const state = useSocketStore.getState()
      if (state.authFailed) return
      if (state.socket && !state.socket.connected) {
        state.socket.connect()
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [enabled])
}
