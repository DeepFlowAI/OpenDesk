import { beforeEach, describe, expect, it, vi } from 'vitest'

const socketMock = vi.hoisted(() => {
  const manager = { on: vi.fn() }
  const socket = {
    auth: { token: '' } as Record<string, unknown>,
    connected: false,
    io: manager,
    on: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
  }
  return {
    socket,
    manager,
    io: vi.fn((_url: string, options: { auth: Record<string, unknown> }) => {
      socket.auth = options.auth
      return socket
    }),
  }
})

vi.mock('socket.io-client', () => ({ io: socketMock.io }))
vi.mock('@/service/base', () => ({ refreshAccessToken: vi.fn() }))
vi.mock('@/utils/auth-log', () => ({ logAuthEvent: vi.fn() }))

import { useSocketStore } from '@/context/socket-store'


beforeEach(() => {
  socketMock.io.mockClear()
  socketMock.manager.on.mockClear()
  socketMock.socket.on.mockClear()
  socketMock.socket.connect.mockClear()
  socketMock.socket.disconnect.mockClear()
  socketMock.socket.auth = { token: '' }
  socketMock.socket.connected = false
  useSocketStore.setState({
    socket: null,
    connected: false,
    connecting: false,
    authFailed: false,
    sessionReplaced: false,
    authFailureToken: null,
  })
})

describe('socket authentication refresh', () => {
  it('keeps a connected socket when the token is unchanged', () => {
    useSocketStore.getState().connect('token-1')
    socketMock.socket.connected = true

    useSocketStore.getState().connect('token-1')

    expect(socketMock.socket.disconnect).not.toHaveBeenCalled()
    expect(socketMock.socket.connect).not.toHaveBeenCalled()
  })

  it('reconnects a connected socket when its token changes', () => {
    useSocketStore.getState().connect('token-1')
    socketMock.socket.connected = true

    useSocketStore.getState().connect('token-2')

    expect(socketMock.socket.auth).toEqual({ token: 'token-2' })
    expect(socketMock.socket.disconnect).toHaveBeenCalledOnce()
    expect(socketMock.socket.connect).toHaveBeenCalledOnce()
  })

  it('drops the socket when the manager gives up reconnecting', () => {
    useSocketStore.getState().connect('token-1')

    const reconnectFailed = socketMock.manager.on.mock.calls
      .find(([event]) => event === 'reconnect_failed')?.[1] as (() => void) | undefined
    expect(reconnectFailed).toBeDefined()

    reconnectFailed!()

    // A null socket lets the workspace effect build a fresh instance instead
    // of holding a dead one until the page reloads.
    expect(useSocketStore.getState().socket).toBeNull()
    expect(useSocketStore.getState().connecting).toBe(false)
    expect(useSocketStore.getState().connected).toBe(false)
  })
})
