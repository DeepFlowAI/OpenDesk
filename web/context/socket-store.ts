import { create } from 'zustand'
import { io, Socket } from 'socket.io-client'
import { refreshAccessToken } from '@/service/base'
import { logAuthEvent } from '@/utils/auth-log'
import { SESSION_REPLACED_CODE } from '@/utils/session-replacement'

const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://localhost:5001'

// Max consecutive refresh-then-reconnect attempts before giving up on auth.
const MAX_AUTH_RETRIES = 5

function isAuthError(err: Error): boolean {
  const msg = err.message?.toLowerCase() ?? ''
  return msg.includes('invalid token') || msg.includes('missing user_id') || msg.includes('session_replaced')
}

function isSessionReplacedError(err: Error): boolean {
  return err.message === SESSION_REPLACED_CODE || err.message?.toLowerCase().includes('session_replaced')
}

function isEmbeddedCallToken(token: string | null): boolean {
  if (!token) return false
  try {
    const payload = token.split('.')[1]
    if (!payload) return false
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(normalized)).typ === 'embedded_call_session'
  } catch {
    return false
  }
}

type SocketState = {
  socket: Socket | null
  connected: boolean
  connecting: boolean
  authFailed: boolean
  sessionReplaced: boolean
  /** Token that triggered authFailed; used to detect a newer cross-tab login. */
  authFailureToken: string | null
  connect: (token: string) => void
  disconnect: () => void
}

function tokenFromSocketAuth(socket: Socket): string | null {
  const auth = socket.auth
  if (auth && typeof auth === 'object' && 'token' in auth) {
    const token = (auth as { token?: unknown }).token
    return typeof token === 'string' && token ? token : null
  }
  return null
}

export const useSocketStore = create<SocketState>((set, get) => ({
  socket: null,
  connected: false,
  connecting: false,
  authFailed: false,
  sessionReplaced: false,
  authFailureToken: null,

  connect: (token: string) => {
    const existing = get().socket
    if (existing) {
      const previousToken = tokenFromSocketAuth(existing)
      existing.auth = { token }
      if (existing.connected && previousToken === token) return

      set({ connecting: true, authFailed: false, sessionReplaced: false, authFailureToken: null })
      if (existing.connected) existing.disconnect()
      existing.connect()
      return
    }

    set({ connecting: true, authFailed: false, sessionReplaced: false, authFailureToken: null })

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
      set({
        connected: true,
        connecting: false,
        authFailed: false,
        sessionReplaced: false,
        authFailureToken: null,
      })
    })

    socket.on('disconnect', () => {
      set({ connected: false })
    })

    // The manager stops retrying once reconnectionAttempts is exhausted (a
    // network outage longer than the backoff window is enough) and emits this
    // only on itself, so the socket-level handlers above never see it. Drop
    // the dead instance so the next connect() builds a fresh one — otherwise
    // the workspace stays silently disconnected until a page reload, and the
    // agent stops receiving calls while still looking ready.
    socket.io.on('reconnect_failed', () => {
      socket.disconnect()
      set({ socket: null, connected: false, connecting: false })
    })

    socket.on('connect_error', async (err: Error) => {
      if (!isAuthError(err)) {
        set({ connecting: false })
        return
      }
      const failureToken = tokenFromSocketAuth(socket)
      if (isEmbeddedCallToken(failureToken)) {
        socket.disconnect()
        set({
          socket: null,
          connected: false,
          connecting: false,
          authFailed: true,
          sessionReplaced: false,
          authFailureToken: failureToken,
        })
        return
      }
      if (isSessionReplacedError(err)) {
        logAuthEvent('socket_auth_failed', {
          error: err.message,
          sessionReplaced: true,
        })
        socket.disconnect()
        set({
          socket: null,
          connected: false,
          connecting: false,
          authFailed: true,
          sessionReplaced: true,
          authFailureToken: failureToken,
        })
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
        set({
          socket: null,
          connected: false,
          connecting: false,
          authFailed: true,
          sessionReplaced: false,
          authFailureToken: failureToken,
        })
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
      if (outcome.status === 'session_replaced') {
        logAuthEvent('socket_auth_failed', {
          error: err.message,
          refreshFailed: true,
          sessionReplaced: true,
        })
        socket.disconnect()
        set({
          socket: null,
          connected: false,
          connecting: false,
          authFailed: true,
          sessionReplaced: true,
          authFailureToken: failureToken,
        })
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
      set({
        socket: null,
        connected: false,
        connecting: false,
        authFailed: true,
        sessionReplaced: false,
        authFailureToken: failureToken,
      })
    })

    set({ socket })
  },

  disconnect: () => {
    const { socket } = get()
    if (socket) {
      socket.disconnect()
      set({
        socket: null,
        connected: false,
        connecting: false,
        sessionReplaced: false,
        authFailureToken: null,
      })
    }
  },
}))
