import { create } from 'zustand'
import { io, Socket } from 'socket.io-client'
import { refreshAccessToken } from '@/service/base'
import { logAuthEvent } from '@/utils/auth-log'

const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://localhost:5001'

// Max consecutive refresh-then-reconnect attempts before giving up on auth.
const MAX_AUTH_RETRIES = 5

function isAuthError(err: Error): boolean {
  const msg = err.message?.toLowerCase() ?? ''
  return msg.includes('invalid token') || msg.includes('missing user_id')
}

type SocketState = {
  socket: Socket | null
  connected: boolean
  connecting: boolean
  authFailed: boolean
  connect: (token: string) => void
  disconnect: () => void
}

export const useSocketStore = create<SocketState>((set, get) => ({
  socket: null,
  connected: false,
  connecting: false,
  authFailed: false,

  connect: (token: string) => {
    const existing = get().socket
    if (existing) {
      if (existing.connected) return

      existing.auth = { token }
      set({ connecting: true, authFailed: false })
      existing.connect()
      return
    }

    set({ connecting: true, authFailed: false })

    // Bound the refresh-then-reconnect loop: if a freshly refreshed token is
    // still rejected, retrying forever just hammers the server. Reset on a
    // successful connect so a genuinely new expiry later still gets its retries.
    let authRetries = 0

    const socket = io(`${SOCKET_URL}/chat`, {
      auth: { token },
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: 10,
    })

    socket.on('connect', () => {
      authRetries = 0
      set({ connected: true, connecting: false, authFailed: false })
    })

    socket.on('disconnect', () => {
      set({ connected: false })
    })

    socket.on('connect_error', async (err: Error) => {
      if (!isAuthError(err)) {
        set({ connecting: false })
        return
      }
      // Refreshed token still rejected too many times — stop, surface auth failure.
      if (authRetries >= MAX_AUTH_RETRIES) {
        logAuthEvent('socket_auth_failed', {
          error: err.message,
          refreshFailed: false,
          exhausted: true,
        })
        socket.disconnect()
        set({ socket: null, connected: false, connecting: false, authFailed: true })
        return
      }
      authRetries += 1
      // Token expired — try to refresh before giving up
      const outcome = await refreshAccessToken()
      if (outcome.status === 'success') {
        socket.auth = { token: outcome.token }
        localStorage.setItem('auth_token', outcome.token)
        socket.connect()
        return
      }
      // Transient refresh failure (network/5xx): keep the session and let the
      // socket's own reconnection loop keep retrying instead of tearing down.
      if (outcome.status === 'transient_error') {
        set({ connecting: false })
        return
      }
      // auth_error / no_token: credentials are invalid — stop reconnecting.
      logAuthEvent('socket_auth_failed', {
        error: err.message,
        refreshFailed: true,
      })
      socket.disconnect()
      set({ socket: null, connected: false, connecting: false, authFailed: true })
    })

    set({ socket })
  },

  disconnect: () => {
    const { socket } = get()
    if (socket) {
      socket.disconnect()
      set({ socket: null, connected: false, connecting: false })
    }
  },
}))
