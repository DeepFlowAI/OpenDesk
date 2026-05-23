import { create } from 'zustand'
import { io, Socket } from 'socket.io-client'
import type { Message } from '@/models/conversation'
import type { SatisfactionSurveyRecord } from '@/models/satisfaction-survey'

const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://localhost:5001'

let optimisticSeq = 0

type VisitorChatState = {
  socket: Socket | null
  connected: boolean
  connecting: boolean

  conversationPublicId: string | null
  messages: Message[]
  hasMore: boolean
  agentTyping: boolean
  activeAgent: { id: number; name: string; avatar: string | null } | null
  satisfactionInvitation: SatisfactionSurveyRecord | null

  visitorId: string | null

  connect: (visitorSessionToken: string, visitorExternalId: string) => void
  disconnect: () => void

  setConversationPublicId: (id: string | null) => void
  setMessages: (msgs: Message[]) => void
  prependMessages: (msgs: Message[]) => void
  addMessage: (msg: Message) => void
  addOptimisticMessage: (conversationPublicId: string, content: string, contentType?: string) => number
  confirmOptimisticMessage: (tempId: number, serverMsg: Message) => void
  markVisitorMessagesRead: (conversationPublicId: string) => void
  setHasMore: (v: boolean) => void
  setAgentTyping: (v: boolean) => void
  setVisitorId: (id: string) => void
  setSatisfactionInvitation: (record: SatisfactionSurveyRecord | null) => void
}

export const useVisitorChatStore = create<VisitorChatState>((set, get) => ({
  socket: null,
  connected: false,
  connecting: false,

  conversationPublicId: null,
  messages: [],
  hasMore: false,
  agentTyping: false,
  activeAgent: null,
  satisfactionInvitation: null,
  visitorId: null,

  connect: (visitorSessionToken, visitorExternalId) => {
    const existing = get().socket
    if (existing) {
      if (existing.connected) return

      existing.auth = {
        visitor_session_token: visitorSessionToken,
      }
      set({ connecting: true, visitorId: visitorExternalId })
      existing.connect()
      return
    }

    set({ connecting: true, visitorId: visitorExternalId })

    const socket = io(`${SOCKET_URL}/visitor`, {
      auth: {
        visitor_session_token: visitorSessionToken,
      },
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

    socket.on('new_message', (msg: Message) => {
      const state = get()

      // Already confirmed via callback — skip duplicate
      const isDuplicate = state.messages.some((m) => m.id === msg.id)
      if (isDuplicate) return

      if (msg.sender_type === 'visitor') {
        // Fallback: replace optimistic placeholder if callback hasn't fired yet
        const idx = state.messages.findIndex(
          (m) => m.id < 0 && m.content === msg.content && m.sender_type === 'visitor',
        )
        if (idx !== -1) {
          const updated = [...state.messages]
          updated[idx] = { ...msg, status: 'delivered' }
          set({ messages: updated })
          return
        }
      }

      // Agent message arrived — clear stale "agent typing" (e.g. send cleared input still emitting typing)
      if (msg.sender_type === 'agent') {
        set({
          messages: [...state.messages, msg],
          agentTyping: false,
          activeAgent: {
            id: msg.sender_id ?? state.activeAgent?.id ?? 0,
            name: msg.sender_name || state.activeAgent?.name || '客服',
            avatar: msg.sender_avatar ?? state.activeAgent?.avatar ?? null,
          },
        })
        return
      }

      set({ messages: [...state.messages, msg] })
    })

    socket.on('agent_typing', () => {
      set({ agentTyping: true })
      setTimeout(() => {
        set({ agentTyping: false })
      }, 5000)
    })

    socket.on('conversation_ended', () => {
      // Keep the conversation public id after closure so post-chat flows, such
      // as satisfaction survey submission, can still address the ended session.
      set({ agentTyping: false })
    })

    socket.on('conversation_assigned', (data: { conversation_public_id?: string; agent?: { id: number; name: string; avatar?: string } }) => {
      const state = get()
      const agentLabel = data.agent?.name || '客服'
      const activeAgent = data.agent
        ? { id: data.agent.id, name: data.agent.name, avatar: data.agent.avatar ?? null }
        : state.activeAgent

      // Replace "等待客服接入..." with the agent-connected message
      const waitIdx = state.messages.findIndex(
        (m) => (m.sender_type === 'system' || m.content_type === 'system') && m.content === '等待客服接入...',
      )
      if (waitIdx !== -1) {
        const updated = [...state.messages]
        updated[waitIdx] = { ...updated[waitIdx], content: `${agentLabel} 已接入会话` }
        set({ messages: updated, activeAgent })
        return
      }

      // Fallback: append a system message
      const sysMsg: Message = {
        id: Date.now(),
        conversation_id: 0,
        conversation_public_id: data.conversation_public_id,
        sender_type: 'system',
        content_type: 'system',
        content: `${agentLabel} 已接入会话`,
        created_at: new Date().toISOString(),
      } as Message
      set({ messages: [...state.messages, sysMsg], activeAgent })
    })

    socket.on('messages_read', (data: { conversation_public_id?: string }) => {
      if (data.conversation_public_id) get().markVisitorMessagesRead(data.conversation_public_id)
    })

    socket.on('satisfaction_invitation_sent', (data: { record?: SatisfactionSurveyRecord }) => {
      if (data.record) set({ satisfactionInvitation: data.record })
    })

    set({ socket })
  },

  disconnect: () => {
    const { socket } = get()
    if (socket) {
      socket.disconnect()
      set({ socket: null, connected: false, connecting: false, activeAgent: null, satisfactionInvitation: null })
    }
  },

  setConversationPublicId: (id) => set({ conversationPublicId: id }),
  setMessages: (msgs) => set({ messages: msgs }),
  prependMessages: (msgs) => set({ messages: [...msgs, ...get().messages] }),

  addMessage: (msg) => {
    const state = get()
    const isDuplicate = state.messages.some((m) => m.id === msg.id)
    if (!isDuplicate) {
      set({ messages: [...state.messages, msg] })
    }
  },

  addOptimisticMessage: (conversationPublicId, content, contentType = 'text') => {
    optimisticSeq -= 1
    const tempId = optimisticSeq
    const msg: Message = {
      id: tempId,
      conversation_id: 0,
      conversation_public_id: conversationPublicId,
      sender_type: 'visitor',
      sender_id: null,
      sender_name: null,
      sender_avatar: null,
      content_type: contentType as Message['content_type'],
      content,
      created_at: new Date().toISOString(),
      status: 'sending',
    }
    set({ messages: [...get().messages, msg] })
    return tempId
  },

  confirmOptimisticMessage: (tempId, serverMsg) => {
    const state = get()
    const updated = state.messages.map((m) =>
      m.id === tempId ? { ...serverMsg, status: 'delivered' as const } : m,
    )
    set({ messages: updated })
  },

  markVisitorMessagesRead: (conversationPublicId) => {
    const state = get()
    const updated = state.messages.map((m) =>
      m.conversation_public_id === conversationPublicId && m.sender_type === 'visitor' && m.status !== 'read'
        ? { ...m, status: 'read' as const }
        : m,
    )
    set({ messages: updated })
  },

  setHasMore: (v) => set({ hasMore: v }),
  setAgentTyping: (v) => set({ agentTyping: v }),
  setVisitorId: (id) => set({ visitorId: id }),
  setSatisfactionInvitation: (record) => set({ satisfactionInvitation: record }),
}))
