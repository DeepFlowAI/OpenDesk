'use client'

import { useEffect, useCallback, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/context/auth-store'
import { useSocketStore } from '@/context/socket-store'
import { useChatStore } from '@/context/chat-store'
import {
  useConversations,
  useAgentStatus,
  useAgentStats,
  agentKeys,
  conversationKeys,
  patchConversationListCache,
} from '@/service/use-conversations'
import { ConversationListPanel } from '@/app/components/features/chat/conversation-list-panel'
import { MessagePanel } from '@/app/components/features/chat/message-panel'
import { AuxiliaryPanel } from '@/app/components/features/chat/auxiliary-panel'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { Message, Conversation } from '@/models/conversation'

const BACKGROUND_MESSAGE_ALERT_SRC = '/audio/notification-alert.mp3'

function buildMessagePreview(msg: Message): string {
  if (msg.content_type === 'text' || msg.content_type === 'system') return msg.content
  if (msg.content_type === 'image') return '[图片]'
  if (msg.content_type === 'file') {
    try {
      const payload = JSON.parse(msg.content) as { name?: string }
      return payload.name ? `[附件] ${payload.name}` : '[附件]'
    } catch {
      return '[附件]'
    }
  }
  return `[${msg.content_type}]`
}

export default function ChatPage() {
  const { token } = useAuthStore()
  const { locale } = useLocaleStore()
  const { socket, connected, connecting, connect } = useSocketStore()
  const queryClient = useQueryClient()
  const { data: convData } = useConversations()
  const { data: agentStatus } = useAgentStatus()
  const { data: agentStats } = useAgentStats()

  const {
    conversations,
    selectedConversationId,
    setConversations,
    selectConversation,
    addConversation,
    updateConversation,
    removeConversation,
    addMessage,
    setVisitorTyping,
  } = useChatStore()

  const typingTimerRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())
  const [ticketDraftConversationIds, setTicketDraftConversationIds] = useState<Set<number>>(new Set())
  const [transferToast, setTransferToast] = useState<string | null>(null)
  const transferToastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const playBackgroundMessageAlert = useCallback(() => {
    if (document.visibilityState === 'visible') return

    const audio = new Audio(BACKGROUND_MESSAGE_ALERT_SRC)
    audio.play().catch(() => {
      // Browsers may block autoplay until the user interacts with the page.
    })
  }, [])

  // Connect Socket.IO on mount
  useEffect(() => {
    if (token && !connected && !connecting) {
      connect(token)
    }
  }, [token, connected, connecting, connect])

  // When the user switches back to this tab after it was backgrounded (and
  // possibly frozen by the browser), check if the socket silently died and
  // force an immediate reconnect + data refresh so the agent is back online
  // within a single frame rather than waiting for the next reconnection tick.
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const sock = useSocketStore.getState().socket
        if (sock && !sock.connected) {
          sock.connect()
        }
        queryClient.invalidateQueries({ queryKey: agentKeys.status })
        queryClient.invalidateQueries({ queryKey: agentKeys.stats })
        queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [queryClient])

  // Sync server conversations to store
  useEffect(() => {
    if (convData?.items) {
      setConversations(convData.items)
    }
  }, [convData, setConversations])

  // Refresh agent state after every (re)connect so the UI mirrors the
  // server-side status once the disconnect grace period was cancelled.
  useEffect(() => {
    if (!socket) return
    const handleConnect = () => {
      queryClient.invalidateQueries({ queryKey: agentKeys.status })
      queryClient.invalidateQueries({ queryKey: agentKeys.stats })
      queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
    }
    socket.on('connect', handleConnect)
    return () => {
      socket.off('connect', handleConnect)
    }
  }, [socket, queryClient])

  // Socket.IO event listeners
  useEffect(() => {
    if (!socket) return

    const handleNewConversation = (data: { conversation_id: number; visitor: Conversation['visitor'] }) => {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'
      fetch(`${apiBase}v1/conversations/${data.conversation_id}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then((conv: Conversation) => addConversation(conv))
        .catch(() => {})
    }

    const handleNewMessage = (msg: Message) => {
      if (msg.sender_type === 'visitor') {
        playBackgroundMessageAlert()
      }
      addMessage(msg.conversation_id, msg)
      const preview = buildMessagePreview(msg)
      const previewSlice = preview.slice(0, 200)
      const baseUpdates: Partial<Conversation> = {
        last_message_at: msg.created_at,
        last_message_preview: previewSlice,
      }
      updateConversation(msg.conversation_id, baseUpdates)
      // Increment unread if not the selected conversation
      const selected = useChatStore.getState().selectedConversationId
      let nextUnread: number | undefined
      if (msg.conversation_id !== selected && msg.sender_type === 'visitor') {
        const conv = useChatStore.getState().conversations.find((c) => c.id === msg.conversation_id)
        if (conv) {
          nextUnread = conv.unread_count + 1
          updateConversation(msg.conversation_id, { unread_count: nextUnread })
        }
      }
      patchConversationListCache(queryClient, msg.conversation_id, {
        ...baseUpdates,
        ...(nextUnread !== undefined ? { unread_count: nextUnread } : {}),
      })
    }

    const handleConversationEnded = (data: { conversation_id: number }) => {
      removeConversation(data.conversation_id)
    }

    const handleConversationTransferred = (data: {
      conversation_id: number
      from_agent_id: number | null
      to_agent_id: number
      conversation?: Conversation
    }) => {
      const me = useAuthStore.getState().user?.id
      if (data.from_agent_id != null && data.from_agent_id === me) {
        removeConversation(data.conversation_id)
      }
      if (data.to_agent_id === me) {
        // Prefer the inline conversation payload so the receiver's list
        // updates without a round-trip; fall back to a REST fetch if older
        // servers (or any partial payload) didn't ship the full record.
        if (data.conversation) {
          addConversation(data.conversation)
        } else {
          const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'
          fetch(`${apiBase}v1/conversations/${data.conversation_id}`, {
            headers: { Authorization: `Bearer ${token}` },
          })
            .then((r) => r.json())
            .then((conv: Conversation) => addConversation(conv))
            .catch(() => {})
        }
        queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
        queryClient.invalidateQueries({ queryKey: agentKeys.stats })
      }
    }

    const handleVisitorTyping = (data: { conversation_id: number }) => {
      setVisitorTyping(data.conversation_id, true)
      const existing = typingTimerRef.current.get(data.conversation_id)
      if (existing) clearTimeout(existing)
      typingTimerRef.current.set(
        data.conversation_id,
        setTimeout(() => setVisitorTyping(data.conversation_id, false), 5000)
      )
    }

    const handleConversationUpdated = (data: {
      conversation_id: number
      last_message_preview?: string
      last_message_at?: string
      unread_count?: number
    }) => {
      const updates: Partial<Conversation> = {}
      if (data.last_message_preview !== undefined) updates.last_message_preview = data.last_message_preview
      if (data.last_message_at !== undefined) updates.last_message_at = data.last_message_at
      if (data.unread_count !== undefined) {
        // The conversation the agent is actively viewing should never carry an
        // unread badge: the server still increments unread on every visitor
        // message and we'd otherwise flash a count until the next mark_read
        // round-trip lands.
        const selected = useChatStore.getState().selectedConversationId
        updates.unread_count = data.conversation_id === selected ? 0 : data.unread_count
      }
      updateConversation(data.conversation_id, updates)
      patchConversationListCache(queryClient, data.conversation_id, updates)
    }

    socket.on('new_conversation', handleNewConversation)
    socket.on('new_message', handleNewMessage)
    socket.on('conversation_ended', handleConversationEnded)
    socket.on('conversation_transferred', handleConversationTransferred)
    socket.on('visitor_typing', handleVisitorTyping)
    socket.on('conversation_updated', handleConversationUpdated)

    return () => {
      socket.off('new_conversation', handleNewConversation)
      socket.off('new_message', handleNewMessage)
      socket.off('conversation_ended', handleConversationEnded)
      socket.off('conversation_transferred', handleConversationTransferred)
      socket.off('visitor_typing', handleVisitorTyping)
      socket.off('conversation_updated', handleConversationUpdated)
    }
  }, [socket, token, queryClient, addConversation, addMessage, updateConversation, removeConversation, setVisitorTyping, playBackgroundMessageAlert])

  const selectedConversation = conversations.find((c) => c.id === selectedConversationId) || null

  const openTicketDraft = useCallback((conversationId: number) => {
    setTicketDraftConversationIds((prev) => new Set(prev).add(conversationId))
  }, [])

  const closeTicketDraft = useCallback((conversationId: number) => {
    setTicketDraftConversationIds((prev) => {
      const next = new Set(prev)
      next.delete(conversationId)
      return next
    })
  }, [])

  const handleTransferred = useCallback(
    (toName: string) => {
      const text = t('ws.chat.transferSuccess', locale, { name: toName })
      setTransferToast(text)
      if (transferToastTimerRef.current) clearTimeout(transferToastTimerRef.current)
      transferToastTimerRef.current = setTimeout(() => setTransferToast(null), 2500)
    },
    [locale],
  )

  useEffect(() => {
    return () => {
      if (transferToastTimerRef.current) clearTimeout(transferToastTimerRef.current)
    }
  }, [])

  return (
    <div className="flex h-full min-h-0 bg-white">
      {/* Connection status bar */}
      {!connected && (
        <div className="absolute left-16 right-0 top-14 z-50 border-b border-amber-200/50 bg-[#f4ebd4] px-4 py-1.5 text-center text-xs text-stone-800">
          {connecting ? t('ws.chat.connecting', locale) : t('ws.chat.connectionLost', locale)}
        </div>
      )}

      {/* Transfer success toast */}
      {transferToast && (
        <div className="pointer-events-none absolute left-1/2 top-20 z-50 -translate-x-1/2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs text-emerald-800 shadow-sm">
          {transferToast}
        </div>
      )}

      {/* Conversation List Panel */}
      <ConversationListPanel
        conversations={conversations}
        selectedId={selectedConversationId}
        onSelect={selectConversation}
        agentStatus={agentStatus || null}
        agentStats={agentStats || null}
      />

      {/* Message Panel */}
      <MessagePanel
        conversation={selectedConversation}
        socket={socket}
        connected={connected}
        onCreateTicket={openTicketDraft}
        onTransferred={handleTransferred}
      />

      {/* Auxiliary Panel */}
      <AuxiliaryPanel
        conversation={selectedConversation}
        ticketDraftOpen={selectedConversation ? ticketDraftConversationIds.has(selectedConversation.id) : false}
        onCloseTicketDraft={closeTicketDraft}
      />
    </div>
  )
}
