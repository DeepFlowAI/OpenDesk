import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Conversation, Message } from '@/models/conversation'

// Window during which a conversation that was recently marked-read locally
// should NOT have its unread_count overridden by stale HTTP responses. This
// shields the local "just read" state from a polling GET that races with the
// server-side reset_unread commit.
const RECENT_READ_WINDOW_MS = 10_000

type ChatState = {
  conversations: Conversation[]
  selectedConversationId: number | null
  messages: Map<number, Message[]>
  visitorTyping: Map<number, boolean>
  recentReadAt: Map<number, number>

  setConversations: (items: Conversation[]) => void
  selectConversation: (id: number | null) => void
  addConversation: (conv: Conversation) => void
  updateConversation: (id: number, updates: Partial<Conversation>) => void
  removeConversation: (id: number) => void
  markConversationRead: (id: number) => void

  setMessages: (conversationId: number, msgs: Message[]) => void
  prependMessages: (conversationId: number, msgs: Message[]) => void
  addMessage: (conversationId: number, msg: Message) => void

  setVisitorTyping: (conversationId: number, typing: boolean) => void
}

function mergeUnreadOnSync(
  serverItems: Conversation[],
  localItems: Conversation[],
  recentReadAt: Map<number, number>,
): Conversation[] {
  const now = Date.now()
  const localById = new Map(localItems.map((c) => [c.id, c]))
  return serverItems.map((srv) => {
    const local = localById.get(srv.id)
    const readAt = recentReadAt.get(srv.id) ?? 0
    const isRecentlyRead = readAt > 0 && now - readAt < RECENT_READ_WINDOW_MS

    // The local copy already reflects either an explicit read action or a
    // socket push newer than the HTTP snapshot. Trust whichever value is
    // smaller (closer to "read") — but only inside the freshness window so a
    // genuinely missed reset can still be repaired by a later poll.
    if (isRecentlyRead && local) {
      return { ...srv, unread_count: Math.min(srv.unread_count, local.unread_count) }
    }
    return srv
  })
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      conversations: [],
      selectedConversationId: null,
      messages: new Map(),
      visitorTyping: new Map(),
      recentReadAt: new Map(),

      setConversations: (items) =>
        set((state) => ({
          conversations: mergeUnreadOnSync(items, state.conversations, state.recentReadAt),
          selectedConversationId:
            state.selectedConversationId == null || items.some((item) => item.id === state.selectedConversationId)
              ? state.selectedConversationId
              : null,
        })),

      selectConversation: (id) =>
        set((state) => {
          if (id == null) return { selectedConversationId: id }
          const nextRecentReadAt = new Map(state.recentReadAt)
          nextRecentReadAt.set(id, Date.now())
          return {
            selectedConversationId: id,
            recentReadAt: nextRecentReadAt,
            conversations: state.conversations.map((c) =>
              c.id === id ? { ...c, unread_count: 0 } : c,
            ),
          }
        }),

      markConversationRead: (id) =>
        set((state) => {
          const nextRecentReadAt = new Map(state.recentReadAt)
          nextRecentReadAt.set(id, Date.now())
          return {
            recentReadAt: nextRecentReadAt,
            conversations: state.conversations.map((c) =>
              c.id === id ? { ...c, unread_count: 0 } : c,
            ),
          }
        }),

      addConversation: (conv) =>
        set((state) => {
          const exists = state.conversations.some((c) => c.id === conv.id)
          if (exists) return state
          return { conversations: [conv, ...state.conversations] }
        }),

      updateConversation: (id, updates) =>
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === id ? { ...c, ...updates } : c
          ),
        })),

      removeConversation: (id) =>
        set((state) => ({
          conversations: state.conversations.filter((c) => c.id !== id),
          selectedConversationId:
            state.selectedConversationId === id ? null : state.selectedConversationId,
        })),

      setMessages: (conversationId, msgs) =>
        set((state) => {
          const map = new Map(state.messages)
          map.set(conversationId, msgs)
          return { messages: map }
        }),

      prependMessages: (conversationId, msgs) =>
        set((state) => {
          const map = new Map(state.messages)
          const existing = map.get(conversationId) || []
          map.set(conversationId, [...msgs, ...existing])
          return { messages: map }
        }),

      addMessage: (conversationId, msg) =>
        set((state) => {
          const map = new Map(state.messages)
          const existing = map.get(conversationId) || []
          const isDuplicate = existing.some((m) => m.id === msg.id)
          if (!isDuplicate) {
            map.set(conversationId, [...existing, msg])
          }
          return { messages: map }
        }),

      setVisitorTyping: (conversationId, typing) =>
        set((state) => {
          const map = new Map(state.visitorTyping)
          map.set(conversationId, typing)
          return { visitorTyping: map }
        }),
    }),
    {
      name: 'workspace-chat',
      partialize: (state) => ({ selectedConversationId: state.selectedConversationId }),
    }
  )
)
