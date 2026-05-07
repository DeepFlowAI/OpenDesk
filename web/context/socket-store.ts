import { create } from 'zustand'
import { io, Socket } from 'socket.io-client'

const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://localhost:5001'

type SocketState = {
  socket: Socket | null
  connected: boolean
  connecting: boolean
  connect: (token: string) => void
  disconnect: () => void
}

export const useSocketStore = create<SocketState>((set, get) => ({
  socket: null,
  connected: false,
  connecting: false,

  connect: (token: string) => {
    const existing = get().socket
    if (existing) {
      if (existing.connected) return

      existing.auth = { token }
      set({ connecting: true })
      existing.connect()
      return
    }

    set({ connecting: true })

    const socket = io(`${SOCKET_URL}/chat`, {
      auth: { token },
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: Infinity,
    })

    socket.on('connect', () => {
      set({ connected: true, connecting: false })
    })

    socket.on('disconnect', () => {
      set({ connected: false })
    })

    socket.on('connect_error', () => {
      set({ connecting: false })
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
