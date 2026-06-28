import { create } from 'zustand'
import { io, Socket } from 'socket.io-client'
import type { Message } from '@/models/conversation'
import type { SatisfactionSurveyRecord } from '@/models/satisfaction-survey'
import type { HumanHandoffEventPayload } from '@/service/use-open-agent-conversation'

const SOCKET_URL = process.env.NEXT_PUBLIC_SOCKET_URL || 'http://localhost:5001'
const VISITOR_PRESENCE_PING_INTERVAL_MS = 8_000

let optimisticSeq = 0
let presencePingTimer: ReturnType<typeof setInterval> | null = null

function mergeMessageUpdate(current: Message, incoming: Message): Message {
  const merged: Message = { ...current, ...incoming }

  if (
    incoming.is_recalled
    && current.sender_type === 'visitor'
    && (current.content_type === 'text' || current.content_type === 'rich_text')
  ) {
    const incomingEditContent = typeof incoming.metadata?.recall_edit_content === 'string'
      ? incoming.metadata.recall_edit_content
      : ''
    const currentEditContent = typeof current.metadata?.recall_edit_content === 'string'
      ? current.metadata.recall_edit_content
      : ''
    const editContent = incomingEditContent || currentEditContent || current.content
    if (editContent.trim()) {
      merged.metadata = {
        ...(current.metadata || {}),
        ...(incoming.metadata || {}),
        recall_edit_content: editContent,
      }
    }
  }

  return merged
}

function stopPresencePing() {
  if (presencePingTimer) {
    clearInterval(presencePingTimer)
    presencePingTimer = null
  }
}

function startPresencePing(socket: Socket) {
  stopPresencePing()
  const ping = () => {
    if (socket.connected) socket.emit('visitor_presence_ping')
  }
  ping()
  presencePingTimer = setInterval(ping, VISITOR_PRESENCE_PING_INTERVAL_MS)
}

type VisitorChatState = {
  socket: Socket | null
  connected: boolean
  connecting: boolean
  authFailed: boolean

  conversationPublicId: string | null
  messages: Message[]
  hasMore: boolean
  agentTyping: boolean
  activeAgent: { id: number; name: string; avatar: string | null } | null
  satisfactionInvitation: SatisfactionSurveyRecord | null
  pendingHumanHandoff: {
    payload: HumanHandoffEventPayload
    brief: string
    messageId?: number
    toolCallId?: string
  } | null
  dismissedHandoffToolCallIds: string[]
  confirmingHandoffToolCallIds: string[]
  handoffRouting: boolean

  visitorId: string | null

  connect: (visitorSessionToken: string, visitorExternalId: string) => void
  disconnect: () => void
  clearAuthFailed: () => void

  setConversationPublicId: (id: string | null) => void
  setMessages: (msgs: Message[]) => void
  prependMessages: (msgs: Message[]) => void
  addMessage: (msg: Message) => void
  updateMessage: (msg: Message) => void
  addOptimisticMessage: (
    conversationPublicId: string,
    content: string,
    contentType?: string,
    metadata?: Record<string, unknown>,
  ) => number
  addBotStreamingMessage: (conversationPublicId: string, senderName: string | null) => number
  appendMessageContent: (messageId: number, delta: string) => void
  setMessageContent: (messageId: number, content: string) => void
  updateMessageMetadata: (
    messageId: number,
    updater: (metadata: Record<string, unknown>) => Record<string, unknown>,
  ) => void
  removeMessage: (messageId: number) => void
  replaceMessage: (messageId: number, serverMsg: Message) => void
  addSystemNotice: (conversationPublicId: string, content: string, metadata?: Record<string, unknown>) => number
  confirmOptimisticMessage: (tempId: number, serverMsg: Message) => void
  markOptimisticDelivered: (tempId: number) => void
  markVisitorMessagesRead: (conversationPublicId: string) => void
  setHasMore: (v: boolean) => void
  setAgentTyping: (v: boolean) => void
  setVisitorId: (id: string) => void
  setSatisfactionInvitation: (record: SatisfactionSurveyRecord | null) => void
  setPendingHumanHandoff: (pending: VisitorChatState['pendingHumanHandoff']) => void
  dismissPendingHumanHandoff: () => void
  markHandoffConfirming: (toolCallId: string) => void
  clearHandoffConfirming: (toolCallId: string) => void
  dismissHandoffByToolCallId: (toolCallId: string) => void
  setHandoffRouting: (routing: boolean) => void
  resetHandoffUiState: () => void
  handleHandoffRouteFailed: (
    reason: string | undefined,
    payload: HumanHandoffEventPayload | null,
    brief: string,
    messageId?: number,
  ) => void
}

type HandoffUiPatch = Partial<
  Pick<
    VisitorChatState,
    | 'pendingHumanHandoff'
    | 'dismissedHandoffToolCallIds'
    | 'confirmingHandoffToolCallIds'
    | 'handoffRouting'
  >
>

const clearedHandoffUiState: HandoffUiPatch = {
  pendingHumanHandoff: null,
  dismissedHandoffToolCallIds: [],
  confirmingHandoffToolCallIds: [],
  handoffRouting: false,
}

function appendUnique(values: string[], value: string): string[] {
  return values.includes(value) ? values : [...values, value]
}

function buildHandoffRouteFailedPatch(
  state: VisitorChatState,
  reason: string | undefined,
  payload: HumanHandoffEventPayload | null,
  brief: string,
  messageId?: number,
): HandoffUiPatch {
  const toolCallId = typeof payload?.tool_call_id === 'string' ? payload.tool_call_id : undefined
  const confirmingIds = toolCallId
    ? state.confirmingHandoffToolCallIds.filter((id) => id !== toolCallId)
    : state.confirmingHandoffToolCallIds

  if (reason === 'internal_error' && payload) {
    return {
      handoffRouting: false,
      confirmingHandoffToolCallIds: confirmingIds,
      pendingHumanHandoff: {
        payload,
        brief: brief.trim() || payload.handoff?.brief?.trim() || '',
        toolCallId,
        messageId,
      },
    }
  }

  if (toolCallId) {
    return {
      pendingHumanHandoff: null,
      dismissedHandoffToolCallIds: appendUnique(state.dismissedHandoffToolCallIds, toolCallId),
      confirmingHandoffToolCallIds: confirmingIds,
      handoffRouting: false,
    }
  }

  return {
    handoffRouting: false,
    confirmingHandoffToolCallIds: confirmingIds,
    pendingHumanHandoff: null,
  }
}

function resolveHandoffMessageUiPatch(state: VisitorChatState, msg: Message): HandoffUiPatch | null {
  const eventType = msg.metadata?.event_type

  if (eventType === 'open_agent_handoff_success') {
    return clearedHandoffUiState
  }

  if (eventType === 'open_agent_handoff_failed') {
    const reason = typeof msg.metadata?.reason === 'string' ? msg.metadata.reason : undefined
    const payload = msg.metadata?.handoff_payload
    const handoffPayload = payload && typeof payload === 'object'
      ? payload as HumanHandoffEventPayload
      : null
    const brief = typeof msg.content === 'string' ? msg.content : ''
    return buildHandoffRouteFailedPatch(state, reason, handoffPayload, brief)
  }

  if (eventType !== 'open_agent_handoff_event') return null

  const handoffEventType = msg.metadata?.handoff_event_type
  if (
    handoffEventType === 'confirm_requested'
    || handoffEventType === undefined
  ) {
    const payload = msg.metadata?.handoff_payload
    if (!payload || typeof payload !== 'object') return null
    const brief = typeof msg.content === 'string' && msg.content.trim()
      ? msg.content.trim()
      : ''
    return {
      pendingHumanHandoff: {
        payload: payload as HumanHandoffEventPayload,
        brief,
        messageId: msg.id,
        toolCallId: typeof msg.metadata?.tool_call_id === 'string'
          ? msg.metadata.tool_call_id
          : undefined,
      },
    }
  }

  if (
    handoffEventType === 'confirmed_by_visitor'
    || handoffEventType === 'auto_triggered'
  ) {
    const toolCallId = typeof msg.metadata?.tool_call_id === 'string'
      ? msg.metadata.tool_call_id
      : null
    return {
      pendingHumanHandoff: null,
      handoffRouting: true,
      confirmingHandoffToolCallIds: toolCallId
        ? state.confirmingHandoffToolCallIds.filter((id) => id !== toolCallId)
        : state.confirmingHandoffToolCallIds,
    }
  }

  return null
}

function isVisitorAuthError(err: Error): boolean {
  const msg = err.message?.toLowerCase() ?? ''
  return msg.includes('visitor_session_token') || msg.includes('invalid visitor session')
}

export const useVisitorChatStore = create<VisitorChatState>((set, get) => ({
  socket: null,
  connected: false,
  connecting: false,
  authFailed: false,

  conversationPublicId: null,
  messages: [],
  hasMore: false,
  agentTyping: false,
  activeAgent: null,
  satisfactionInvitation: null,
  pendingHumanHandoff: null,
  dismissedHandoffToolCallIds: [],
  confirmingHandoffToolCallIds: [],
  handoffRouting: false,
  visitorId: null,

  connect: (visitorSessionToken, visitorExternalId) => {
    const existing = get().socket
    if (existing) {
      if (existing.connected) return

      existing.auth = {
        visitor_session_token: visitorSessionToken,
      }
      set({ connecting: true, authFailed: false, visitorId: visitorExternalId })
      existing.connect()
      return
    }

    set({ connecting: true, authFailed: false, visitorId: visitorExternalId })

    const socket = io(`${SOCKET_URL}/visitor`, {
      auth: {
        visitor_session_token: visitorSessionToken,
      },
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: 10,
    })

    socket.on('connect', () => {
      startPresencePing(socket)
      set({ connected: true, connecting: false, authFailed: false })
    })

    socket.on('disconnect', () => {
      stopPresencePing()
      set({ connected: false })
    })

    socket.on('connect_error', (err: Error) => {
      // Invalid/expired visitor session: the token won't fix itself by
      // retrying, so stop and let the page surface it instead of spinning in a
      // reconnect loop that re-fires on every `connecting: false`.
      if (isVisitorAuthError(err)) {
        stopPresencePing()
        socket.disconnect()
        set({ socket: null, connected: false, connecting: false, authFailed: true })
        return
      }
      set({ connecting: false })
    })

    socket.on('new_message', (msg: Message) => {
      const state = get()
      const handoffPatch = resolveHandoffMessageUiPatch(state, msg)

      // Already confirmed via callback — skip duplicate
      const isDuplicate = state.messages.some((m) => m.id === msg.id)
      if (isDuplicate) {
        if (handoffPatch) set(handoffPatch)
        return
      }

      if (msg.sender_type === 'visitor') {
        // Fallback: replace optimistic placeholder if callback hasn't fired yet
        const idx = state.messages.findIndex(
          (m) => m.id < 0 && m.content === msg.content && m.sender_type === 'visitor',
        )
        if (idx !== -1) {
          const updated = [...state.messages]
          updated[idx] = { ...msg, status: msg.status ?? 'delivered' }
          set({ messages: updated })
          return
        }
      }

      if (msg.sender_type === 'bot') {
        const pendingBotIdx = state.messages.findIndex(
          (m) =>
            m.id < 0
            && m.sender_type === 'bot'
            && (
              !msg.conversation_public_id
              || !m.conversation_public_id
              || m.conversation_public_id === msg.conversation_public_id
            ),
        )
        if (pendingBotIdx !== -1) {
          const updated = [...state.messages]
          updated[pendingBotIdx] = msg
          set({
            messages: updated,
            agentTyping: false,
            activeAgent: {
              id: msg.sender_id ?? state.activeAgent?.id ?? 0,
              name: msg.sender_name || state.activeAgent?.name || '客服',
              avatar: msg.sender_avatar ?? state.activeAgent?.avatar ?? null,
            },
            ...handoffPatch,
          })
          return
        }
      }

      // Agent message arrived — clear stale "agent typing" (e.g. send cleared input still emitting typing)
      if (msg.sender_type === 'agent' || msg.sender_type === 'bot') {
        set({
          messages: [...state.messages, msg],
          agentTyping: false,
          activeAgent: {
            id: msg.sender_id ?? state.activeAgent?.id ?? 0,
            name: msg.sender_name || state.activeAgent?.name || '客服',
            avatar: msg.sender_avatar ?? state.activeAgent?.avatar ?? null,
          },
          ...handoffPatch,
        })
        return
      }

      set({ messages: [...state.messages, msg], ...handoffPatch })
    })

    socket.on('message_recalled', (msg: Message) => {
      get().updateMessage(msg)
    })

    socket.on('agent_typing', (data?: { stop?: boolean }) => {
      if (data?.stop) {
        set({ agentTyping: false })
        return
      }
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
      const activeAgent = data.agent
        ? { id: data.agent.id, name: data.agent.name, avatar: data.agent.avatar ?? null }
        : state.activeAgent

      // The "agent joined" timeline event is persisted server-side and delivered
      // via `new_message`, preserving its own timestamp. Here we only update the
      // active agent and clear any pending handoff UI.
      set({ activeAgent, ...clearedHandoffUiState })
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
      stopPresencePing()
      socket.disconnect()
      set({
        socket: null,
        connected: false,
        connecting: false,
        activeAgent: null,
        satisfactionInvitation: null,
        pendingHumanHandoff: null,
        dismissedHandoffToolCallIds: [],
        confirmingHandoffToolCallIds: [],
        handoffRouting: false,
      })
    }
  },

  // Let the page retry after an auth failure: it mints a fresh visitor session
  // token, then flips this back so the connect effect can reconnect.
  clearAuthFailed: () => set({ authFailed: false }),

  setConversationPublicId: (id) => set({ conversationPublicId: id }),
  setMessages: (msgs) => set({ messages: msgs }),
  prependMessages: (msgs) => set({ messages: [...msgs, ...get().messages] }),

  addMessage: (msg) => {
    const state = get()
    const isDuplicate = state.messages.some((m) => m.id === msg.id)
    const handoffPatch = resolveHandoffMessageUiPatch(state, msg)
    if (!isDuplicate) {
      set({ messages: [...state.messages, msg], ...handoffPatch })
    } else if (handoffPatch) {
      set(handoffPatch)
    }
  },

  updateMessage: (msg) => {
    const state = get()
    set({
      messages: state.messages.map((message) =>
        message.id === msg.id ? mergeMessageUpdate(message, msg) : message,
      ),
    })
  },

  addOptimisticMessage: (conversationPublicId, content, contentType = 'text', metadata) => {
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
      metadata,
      created_at: new Date().toISOString(),
      status: 'sending',
    }
    set({ messages: [...get().messages, msg] })
    return tempId
  },

  addBotStreamingMessage: (conversationPublicId, senderName) => {
    optimisticSeq -= 1
    const tempId = optimisticSeq
    const msg: Message = {
      id: tempId,
      conversation_id: 0,
      conversation_public_id: conversationPublicId,
      sender_type: 'bot',
      sender_id: null,
      sender_name: senderName || '智能助手',
      sender_avatar: null,
      content_type: 'text',
      content: '',
      created_at: new Date().toISOString(),
      metadata: { streaming: true },
    }
    set({ messages: [...get().messages, msg] })
    return tempId
  },

  appendMessageContent: (messageId, delta) => {
    if (!delta) return
    const updated = get().messages.map((m) =>
      m.id === messageId ? { ...m, content: `${m.content}${delta}` } : m,
    )
    set({ messages: updated })
  },

  setMessageContent: (messageId, content) => {
    const updated = get().messages.map((m) =>
      m.id === messageId ? { ...m, content } : m,
    )
    set({ messages: updated })
  },

  updateMessageMetadata: (messageId, updater) => {
    const updated = get().messages.map((m) =>
      m.id === messageId ? { ...m, metadata: updater(m.metadata || {}) } : m,
    )
    set({ messages: updated })
  },

  removeMessage: (messageId) => {
    set({ messages: get().messages.filter((m) => m.id !== messageId) })
  },

  replaceMessage: (messageId, serverMsg) => {
    const state = get()
    const exists = state.messages.some((m) => m.id === serverMsg.id)
    if (exists) {
      set({ messages: state.messages.filter((m) => m.id !== messageId) })
      return
    }
    set({
      messages: state.messages.map((m) => (m.id === messageId ? serverMsg : m)),
    })
  },

  addSystemNotice: (conversationPublicId, content, metadata = {}) => {
    optimisticSeq -= 1
    const tempId = optimisticSeq
    const msg: Message = {
      id: tempId,
      conversation_id: 0,
      conversation_public_id: conversationPublicId,
      sender_type: 'system',
      sender_id: null,
      sender_name: null,
      sender_avatar: null,
      content_type: 'system',
      content,
      metadata,
      created_at: new Date().toISOString(),
    }
    set({ messages: [...get().messages, msg] })
    return tempId
  },

  confirmOptimisticMessage: (tempId, serverMsg) => {
    const state = get()
    const updated = state.messages.map((m) =>
      m.id === tempId ? { ...serverMsg, status: serverMsg.status ?? 'delivered' as const } : m,
    )
    set({ messages: updated })
  },

  markOptimisticDelivered: (tempId) => {
    const updated = get().messages.map((m) =>
      m.id === tempId ? { ...m, status: 'delivered' as const } : m,
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
  setPendingHumanHandoff: (pending) => set({ pendingHumanHandoff: pending }),
  dismissPendingHumanHandoff: () => {
    const pending = get().pendingHumanHandoff
    const conversationPublicId = get().conversationPublicId
    const socket = get().socket

    if (pending?.toolCallId) {
      set({
        pendingHumanHandoff: null,
        dismissedHandoffToolCallIds: [
          ...get().dismissedHandoffToolCallIds,
          pending.toolCallId,
        ],
        confirmingHandoffToolCallIds: get().confirmingHandoffToolCallIds.filter(
          (id) => id !== pending.toolCallId,
        ),
      })
    } else if (pending?.messageId != null) {
      set({
        pendingHumanHandoff: null,
        dismissedHandoffToolCallIds: [
          ...get().dismissedHandoffToolCallIds,
          `message_${pending.messageId}`,
        ],
      })
    } else {
      set({ pendingHumanHandoff: null })
    }

    if (socket?.connected && conversationPublicId) {
      socket.emit('dismiss_human_handoff', {
        conversation_public_id: conversationPublicId,
        ...(pending?.toolCallId ? { tool_call_id: pending.toolCallId } : {}),
      })
    }
  },
  markHandoffConfirming: (toolCallId) => {
    if (!toolCallId) return
    set({
      handoffRouting: true,
      confirmingHandoffToolCallIds: get().confirmingHandoffToolCallIds.includes(toolCallId)
        ? get().confirmingHandoffToolCallIds
        : [...get().confirmingHandoffToolCallIds, toolCallId],
    })
  },
  clearHandoffConfirming: (toolCallId) => {
    set({
      confirmingHandoffToolCallIds: get().confirmingHandoffToolCallIds.filter((id) => id !== toolCallId),
    })
  },
  dismissHandoffByToolCallId: (toolCallId) => {
    set({
      pendingHumanHandoff: null,
      dismissedHandoffToolCallIds: get().dismissedHandoffToolCallIds.includes(toolCallId)
        ? get().dismissedHandoffToolCallIds
        : [...get().dismissedHandoffToolCallIds, toolCallId],
      confirmingHandoffToolCallIds: get().confirmingHandoffToolCallIds.filter((id) => id !== toolCallId),
      handoffRouting: false,
    })
  },
  setHandoffRouting: (routing) => set({ handoffRouting: routing }),
  resetHandoffUiState: () => set({
    pendingHumanHandoff: null,
    dismissedHandoffToolCallIds: [],
    confirmingHandoffToolCallIds: [],
    handoffRouting: false,
  }),
  handleHandoffRouteFailed: (reason, payload, brief, messageId) => {
    set(buildHandoffRouteFailedPatch(get(), reason, payload, brief, messageId))
  },
}))
