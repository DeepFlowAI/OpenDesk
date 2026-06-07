'use client'

import { useState, useRef, useEffect, useCallback, useLayoutEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { IconMessageCircle } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { useChatStore } from '@/context/chat-store'
import { useMessages, conversationKeys, fetchConversationHistory } from '@/service/use-conversations'
import { useConversationSatisfaction, useSendSatisfactionInvitation } from '@/service/use-satisfaction-survey'
import { AgentChatRuntimeProvider } from '@/components/assistant-ui/agent-chat-runtime'
import { AgentThread } from '@/components/assistant-ui/agent-thread'
import { t } from '@/utils/i18n'
import { hasPermission } from '@/utils/permissions'
import type { Conversation, WorkspaceConversationHistoryItem } from '@/models/conversation'
import type { Socket } from 'socket.io-client'

const HISTORY_PAGE_SIZE = 10
const HISTORY_CLIENT_LIMIT = 200

type ConversationHistoryCache = {
  conversations: WorkspaceConversationHistoryItem[]
  hasMore: boolean
  loaded: boolean
  error: boolean
  limitReached: boolean
}

type Props = {
  conversation: Conversation | null
  socket: Socket | null
  connected: boolean
  onCreateTicket?: (conversationId: number) => void
  onTransferred?: (toName: string) => void
}

export function MessagePanel({
  conversation,
  socket,
  connected,
  onCreateTicket,
  onTransferred,
}: Props) {
  const { locale } = useLocaleStore()
  const currentUser = useAuthStore((state) => state.user)
  const queryClient = useQueryClient()
  const { messages, setMessages, visitorTyping, visitorTypingContent, markConversationRead } = useChatStore()
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [historyConversations, setHistoryConversations] = useState<WorkspaceConversationHistoryItem[]>([])
  const [historyHasMore, setHistoryHasMore] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [historyError, setHistoryError] = useState(false)
  const [historyLimitReached, setHistoryLimitReached] = useState(false)
  const prevConvIdRef = useRef<number>(0)
  const historyCacheRef = useRef<Map<number, ConversationHistoryCache>>(new Map())

  const convId = conversation?.id || 0
  const currentMessages = messages.get(convId) || []
  const isTyping = visitorTyping.get(convId) || false
  const typingContent = visitorTypingContent.get(convId) || ''
  const isClosed = conversation?.status === 'closed'
  const canCreateTicket = hasPermission(currentUser, 'ticket.workspace.create')
  const canTransfer = hasPermission(currentUser, 'chat.conversation.transfer')

  // Force refetch when switching conversations
  useLayoutEffect(() => {
    if (convId && convId !== prevConvIdRef.current) {
      prevConvIdRef.current = convId
      const cachedHistory = historyCacheRef.current.get(convId)
      setHistoryConversations(cachedHistory?.conversations ?? [])
      setHistoryHasMore(cachedHistory?.hasMore ?? false)
      setHistoryLoading(false)
      setHistoryLoaded(cachedHistory?.loaded ?? false)
      setHistoryError(cachedHistory?.error ?? false)
      setHistoryLimitReached(cachedHistory?.limitReached ?? false)
      queryClient.invalidateQueries({ queryKey: conversationKeys.messages(convId) })
    }
  }, [convId, queryClient])

  // Fetch initial messages
  const { data: msgData } = useMessages(convId)
  const { data: satisfactionState, isLoading: satisfactionLoading } = useConversationSatisfaction(convId)
  const sendSatisfaction = useSendSatisfactionInvitation(convId)

  const handleSendSatisfaction = useCallback(async () => {
    if (!convId || sendSatisfaction.isPending) return false
    try {
      const state = await sendSatisfaction.mutateAsync({ force: false })
      if (state.needs_confirmation) {
        const confirmed = window.confirm(t('ws.chat.satisfactionResendConfirm', locale))
        if (!confirmed) return false
        await sendSatisfaction.mutateAsync({ force: true })
      }
      queryClient.invalidateQueries({ queryKey: conversationKeys.messages(convId) })
      return true
    } catch {
      window.alert(t('ws.chat.satisfactionSendFailed', locale))
      return false
    }
  }, [convId, locale, queryClient, sendSatisfaction])

  useEffect(() => {
    if (msgData && convId) {
      setMessages(convId, msgData.items)
      setHasMore(msgData.has_more)
    }
  }, [msgData, convId, setMessages])

  // Mark messages as read when the agent opens a conversation. The local
  // read-state shield is updated synchronously so a polling GET racing with
  // the server-side reset cannot revive the unread badge.
  useEffect(() => {
    if (!socket || !convId || !connected) return
    socket.emit('mark_read', { conversation_id: convId })
    markConversationRead(convId)
  }, [socket, convId, connected, markConversationRead])

  // Load more messages
  const handleLoadMore = useCallback(async () => {
    if (!convId || loadingMore || !hasMore) return
    const oldest = currentMessages[0]
    if (!oldest) return
    setLoadingMore(true)
    try {
      const { get: apiGet } = await import('@/service/base')
      const data = await apiGet<{ items: typeof currentMessages; has_more: boolean }>(
        `v1/conversations/${convId}/messages`,
        { searchParams: { before_id: oldest.id, limit: 20 } },
      )
      useChatStore.getState().prependMessages(convId, data.items)
      setHasMore(data.has_more)
    } catch {
      // ignore
    } finally {
      setLoadingMore(false)
    }
  }, [convId, loadingMore, hasMore, currentMessages])

  const handleLoadHistory = useCallback(
    async (beforeId?: number) => {
      if (!convId || historyLoading || historyLimitReached) return
      setHistoryLoading(true)
      setHistoryError(false)
      try {
        const data = await fetchConversationHistory({
          conversationId: convId,
          beforeId,
          limit: HISTORY_PAGE_SIZE,
        })
        const chronologicalItems = [...data.items].reverse()
        const nextConversations = beforeId
          ? [...chronologicalItems, ...historyConversations]
          : chronologicalItems
        const nextCount = beforeId
          ? nextConversations.length
          : chronologicalItems.length
        const nextLimitReached = nextCount >= HISTORY_CLIENT_LIMIT
        historyCacheRef.current.set(convId, {
          conversations: nextConversations,
          hasMore: data.has_more,
          loaded: true,
          error: false,
          limitReached: nextLimitReached,
        })
        if (prevConvIdRef.current !== convId) return
        setHistoryConversations(nextConversations)
        setHistoryHasMore(data.has_more)
        setHistoryLoaded(true)
        setHistoryLimitReached(nextLimitReached)
      } catch {
        historyCacheRef.current.set(convId, {
          conversations: historyConversations,
          hasMore: historyHasMore,
          loaded: historyLoaded,
          error: true,
          limitReached: historyLimitReached,
        })
        if (prevConvIdRef.current !== convId) return
        setHistoryError(true)
      } finally {
        if (prevConvIdRef.current === convId) {
          setHistoryLoading(false)
        }
      }
    },
    [
      convId,
      historyConversations,
      historyHasMore,
      historyLimitReached,
      historyLoaded,
      historyLoading,
    ],
  )

  // Empty state — no conversation selected
  if (!conversation) {
    return (
      <div className="flex min-h-0 min-w-0 flex-1 flex-col items-center justify-center bg-white">
        <div className="flex flex-col items-center gap-4 text-center">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-[#F5F5F5]">
            <IconMessageCircle size={32} className="text-[#999999]" />
          </div>
          <p className="text-sm text-[#737373]">{t('ws.chat.selectHint', locale)}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      <AgentChatRuntimeProvider
        socket={socket}
        conversation={conversation}
        locale={locale}
        isClosed={isClosed || false}
        isTyping={isTyping}
        visitorTypingContent={typingContent}
        hasMore={hasMore}
        loadingMore={loadingMore}
        historyAvailable={Boolean(conversation.has_history_conversations || historyConversations.length > 0)}
        historyConversations={historyConversations}
        historyHasMore={historyHasMore}
        historyLoading={historyLoading}
        historyLoaded={historyLoaded}
        historyError={historyError}
        historyLimitReached={historyLimitReached}
        onLoadMore={handleLoadMore}
        onLoadHistory={handleLoadHistory}
        onEndConversation={() => {
          if (socket) socket.emit('end_conversation', { conversation_id: convId })
        }}
        onCreateTicket={() => onCreateTicket?.(convId)}
        canCreateTicket={canCreateTicket}
        canTransfer={canTransfer}
        onTransferred={(toName) => onTransferred?.(toName)}
        satisfactionState={satisfactionState ?? null}
        satisfactionLoading={satisfactionLoading}
        satisfactionSending={sendSatisfaction.isPending}
        onSendSatisfaction={handleSendSatisfaction}
      >
        <div className="flex min-h-0 min-w-0 flex-1 flex-col bg-white">
          <AgentThread socket={socket} />
        </div>
      </AgentChatRuntimeProvider>
    </div>
  )
}
