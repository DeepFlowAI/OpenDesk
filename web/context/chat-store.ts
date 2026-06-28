import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Conversation, Message } from '@/models/conversation'

export type WorkspaceConversationScope = 'my' | 'peers'
export type WorkspaceMyConversationView = 'current' | 'collaborating' | 'history'
export type WorkspaceChatTab = 'messages' | 'offline' | 'queue'

// Window during which a conversation that was recently marked-read locally
// should NOT have its unread_count overridden by stale HTTP responses. This
// shields the local "just read" state from a polling GET that races with the
// server-side reset_unread commit.
const RECENT_READ_WINDOW_MS = 10_000

type ChatState = {
  conversations: Conversation[]
  selectedConversationId: number | null
  conversationScope: WorkspaceConversationScope
  myConversationView: WorkspaceMyConversationView
  workspaceChatTab: WorkspaceChatTab
  messages: Map<number, Message[]>
  visitorTyping: Map<number, boolean>
  visitorTypingContent: Map<number, string>
  recentReadAt: Map<number, number>

  setConversations: (items: Conversation[]) => void
  selectConversation: (id: number | null) => void
  setConversationScope: (scope: WorkspaceConversationScope) => void
  setMyConversationView: (view: WorkspaceMyConversationView) => void
  setWorkspaceChatTab: (tab: WorkspaceChatTab) => void
  addConversation: (conv: Conversation) => void
  updateConversation: (id: number, updates: Partial<Conversation>) => void
  removeConversation: (id: number) => void
  markConversationRead: (id: number) => void

  setMessages: (conversationId: number, msgs: Message[]) => void
  prependMessages: (conversationId: number, msgs: Message[]) => void
  addMessage: (conversationId: number, msg: Message) => void
  updateMessage: (conversationId: number, msg: Message) => void
  markAgentMessagesReadByVisitor: (conversationId: number, messageIds?: number[]) => void

  setVisitorTyping: (conversationId: number, typing: boolean, content?: string) => void
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
      conversationScope: 'my',
      myConversationView: 'current',
      workspaceChatTab: 'messages',
      messages: new Map(),
      visitorTyping: new Map(),
      visitorTypingContent: new Map(),
      recentReadAt: new Map(),

      setConversations: (items) =>
        set((state) => ({
          // Drop closed conversations defensively: a stale list refetch that
          // races a just-ended conversation must not resurrect it into the
          // active list.
          conversations: mergeUnreadOnSync(
            items,
            state.conversations,
            state.recentReadAt,
          ).filter((conversation) => conversation.status !== 'closed'),
          selectedConversationId: state.selectedConversationId,
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

      setConversationScope: (scope) => set({ conversationScope: scope }),
      setMyConversationView: (view) => set({ myConversationView: view }),
      setWorkspaceChatTab: (tab) => set({ workspaceChatTab: tab }),

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

      updateMessage: (conversationId, msg) =>
        set((state) => {
          const map = new Map(state.messages)
          const existing = map.get(conversationId) || []
          map.set(
            conversationId,
            existing.map((message) => (message.id === msg.id ? { ...message, ...msg } : message)),
          )
          return { messages: map }
        }),

      markAgentMessagesReadByVisitor: (conversationId, messageIds) =>
        set((state) => {
          const map = new Map(state.messages)
          const existing = map.get(conversationId) || []
          if (existing.length === 0) return state
          const idSet = messageIds && messageIds.length > 0 ? new Set(messageIds) : null
          map.set(
            conversationId,
            existing.map((message) => {
              if (message.sender_type !== 'agent') return message
              if (idSet && !idSet.has(message.id)) return message
              return message.status === 'read' ? message : { ...message, status: 'read' }
            }),
          )
          return { messages: map }
        }),

      setVisitorTyping: (conversationId, typing, content) =>
        set((state) => {
          const typingMap = new Map(state.visitorTyping)
          const contentMap = new Map(state.visitorTypingContent)
          typingMap.set(conversationId, typing)
          if (typing && content !== undefined) {
            contentMap.set(conversationId, content)
          } else if (!typing) {
            contentMap.delete(conversationId)
          }
          return { visitorTyping: typingMap, visitorTypingContent: contentMap }
        }),
    }),
    {
      name: 'workspace-chat',
      partialize: (state) => ({
        selectedConversationId: state.selectedConversationId,
        conversationScope: state.conversationScope,
        myConversationView: state.myConversationView,
        workspaceChatTab: state.workspaceChatTab,
      }),
    }
  )
)
