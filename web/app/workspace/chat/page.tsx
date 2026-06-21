'use client'

import {
  useEffect,
  useCallback,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/context/auth-store'
import { useSocketStore } from '@/context/socket-store'
import { useChatStore } from '@/context/chat-store'
import {
  useConversations,
  useConversationHistory,
  useAgentStatus,
  useAgentStats,
  useStartConversationFromHistory,
  agentKeys,
  conversationKeys,
  patchConversationListCache,
  type ConversationListScope,
} from '@/service/use-conversations'
import { get } from '@/service/base'
import { useUpdateCurrentUserPreferences } from '@/service/use-auth'
import {
  useQueueTasks,
  useQueueTaskCount,
  getNextQueueTaskId,
  queueWorkspaceKeys,
} from '@/service/use-queue-workspace'
import {
  ConversationListPanel,
  type MyConversationView,
  type ConversationPanelTab,
} from '@/app/components/features/chat/conversation-list-panel'
import { MessagePanel } from '@/app/components/features/chat/message-panel'
import { AuxiliaryPanel } from '@/app/components/features/chat/auxiliary-panel'
import { MessageSearchPanel } from '@/app/components/features/chat/message-search-panel'
import {
  QueueTaskListSidebar,
  QueueTaskPanel,
} from '@/app/components/features/chat/queue-task-panel'
import {
  OfflineMessageDetailPanel,
  OfflineMessageListSidebar,
} from '@/app/components/features/offline-messages/offline-message-panel'
import {
  getNextPendingOfflineMessageId,
  offlineMessageKeys,
  removePendingOfflineMessageFromListCache,
  useOfflineMessageCount,
  useOfflineMessages,
} from '@/service/use-offline-messages'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { getDataScope, hasPermission } from '@/utils/permissions'
import type { Message, Conversation, AgentStats } from '@/models/conversation'
import { isWelcomeLikeContentType } from '@/lib/welcome-message-content-type'
import type { OfflineMessageConvertResponse } from '@/models/offline-message'
import type { OfflineMessageListResponse } from '@/models/offline-message'
import type { QueueAssignmentWorkspaceResponse } from '@/models/queue-workspace'
import type { ComposerInsertRequest } from '@/components/assistant-ui/agent-composer'
import { useWorkspaceNotificationAlert } from '@/hooks/use-workspace-notification-alert'

type QueueUpdatedEvent = {
  action?: string
  task_id?: number | null
  queue_type?: string | null
  queue_id?: number | null
}

type ConversationListUpdatedEvent = {
  action?: string
  conversation_id?: number | null
  updated_at?: string
}

type OfflineMessageUpdatedEvent = {
  action?: string
  offline_message_id?: number | null
  status?: string | null
  target_group_id?: number | null
  last_message_at?: string | null
  message_count?: number | null
}

const AUXILIARY_PANEL_DEFAULT_WIDTH = 300
const AUXILIARY_PANEL_MIN_WIDTH = 260
const AUXILIARY_PANEL_MAX_WIDTH = 520
const CONVERSATION_LIST_PANEL_WIDTH = 280
const MESSAGE_PANEL_MIN_WIDTH = 420
const RESIZE_HANDLE_WIDTH = 1

function clampAuxiliaryPanelWidth(width: number, maxWidth = AUXILIARY_PANEL_MAX_WIDTH): number {
  return Math.min(maxWidth, Math.max(AUXILIARY_PANEL_MIN_WIDTH, width))
}

function buildMessagePreview(msg: Message, locale: 'zh' | 'en'): string {
  if (msg.content_type === 'internal_note') {
    const prefix = locale === 'zh' ? '[内部]' : '[Internal]'
    return `${prefix} ${msg.content}`
  }
  if (msg.content_type === 'text' || msg.content_type === 'system') return msg.content
  if (isWelcomeLikeContentType(msg.content_type)) {
    return msg.content
      .replace(/<[^>]*>/g, ' ')
      .replace(/&nbsp;/g, ' ')
      .replace(/\s+/g, ' ')
      .trim() || '欢迎语'
  }
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
  const { token, user } = useAuthStore()
  const { locale } = useLocaleStore()
  const { socket, connected, connecting, authFailed, connect } = useSocketStore()
  const queryClient = useQueryClient()
  const [conversationScope, setConversationScope] = useState<ConversationListScope>('my')
  const [myConversationView, setMyConversationView] = useState<MyConversationView>('current')
  const peerConversationScope = getDataScope(user, 'chat.conversation.peer.view')
  const canPeerTab = hasPermission(user, 'chat.conversation.peer.view') && peerConversationScope !== 'self'
  const canOfflineMessages = hasPermission(user, 'chat.offline_message.view')
  const canQueueTab = hasPermission(user, 'chat.queue.view')
  const [workspaceChatTab, setWorkspaceChatTab] = useState<'messages' | 'offline' | 'queue'>('messages')
  const [selectedOfflineMessageId, setSelectedOfflineMessageId] = useState<number | null>(null)
  const skipOfflineAutoSelectRef = useRef(false)
  const [selectedQueueTaskId, setSelectedQueueTaskId] = useState<number | null>(null)
  const skipQueueAutoSelectRef = useRef(false)
  const [queueFilter, setQueueFilter] = useState<{ queueType: string | null; queueId: number | null }>({
    queueType: null,
    queueId: null,
  })
  const isOfflineTabActive = workspaceChatTab === 'offline'
  const isQueueTabActive = workspaceChatTab === 'queue'
  const isMessagesTabActive = workspaceChatTab === 'messages'
  const isPeerTabActive = isMessagesTabActive && conversationScope === 'peers'
  const myConversationsQuery = useConversations({ scope: 'my' })
  const peerConversationsQuery = useConversations({ scope: 'peers', enabled: canPeerTab && isPeerTabActive })
  const offlineMessageCountQuery = useOfflineMessageCount({ status: 'pending', enabled: canOfflineMessages })
  const offlineMessagesQuery = useOfflineMessages({
    status: 'pending',
    enabled: canOfflineMessages && isOfflineTabActive,
  })
  const queueTaskCountQuery = useQueueTaskCount({ enabled: canQueueTab })
  const queueTasksQuery = useQueueTasks({
    enabled: canQueueTab && isQueueTabActive,
    queueType: queueFilter.queueType,
    queueId: queueFilter.queueId,
  })
  const offlineMessageItems = useMemo(
    () => offlineMessagesQuery.data?.items ?? [],
    [offlineMessagesQuery.data?.items],
  )
  const queueTaskItems = useMemo(
    () => queueTasksQuery.data?.items ?? [],
    [queueTasksQuery.data?.items],
  )
  const activeConversationsQuery = conversationScope === 'peers' ? peerConversationsQuery : myConversationsQuery
  const convData = activeConversationsQuery.data
  const isMyHistoryActive =
    isMessagesTabActive && conversationScope === 'my' && myConversationView === 'history'
  const historyConversationsQuery = useConversationHistory({ enabled: isMyHistoryActive })
  const historyConversations = useMemo(
    () => historyConversationsQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [historyConversationsQuery.data?.pages],
  )
  const { data: agentStatus } = useAgentStatus()
  const { data: agentStats } = useAgentStats()
  const startConversationFromHistory = useStartConversationFromHistory()

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
    markConversationRead,
  } = useChatStore()

  const typingTimerRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map())
  const [ticketDraftConversationIds, setTicketDraftConversationIds] = useState<Set<number>>(new Set())
  const [transferToast, setTransferToast] = useState<string | null>(null)
  const [composerInsertRequest, setComposerInsertRequest] = useState<ComposerInsertRequest | null>(null)
  const [selectedConversationSnapshot, setSelectedConversationSnapshot] = useState<Conversation | null>(null)
  const [messageSearchOpen, setMessageSearchOpen] = useState(false)
  const transferToastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { playMessageAlert, playSessionAlert } = useWorkspaceNotificationAlert()
  // Tracks the currently opened peer conversation so socket handlers can skip
  // its unread badge and notification sound without stale closures.
  const selectedPeerConversationIdRef = useRef<number | null>(null)
  const chatShellRef = useRef<HTMLDivElement | null>(null)
  const [auxiliaryPanelWidth, setAuxiliaryPanelWidth] = useState(AUXILIARY_PANEL_DEFAULT_WIDTH)
  const [auxiliaryPanelResizing, setAuxiliaryPanelResizing] = useState(false)
  const updateCurrentUserPreferences = useUpdateCurrentUserPreferences()
  const workspaceChatPreferences = user?.preferences?.workspace_chat

  const saveWorkspaceChatPreference = useCallback(
    (preference: { auxiliary_panel_width?: number; composer_input_height?: number }) => {
      if (!user) return
      const preferences = {
        ...user.preferences,
        workspace_chat: {
          ...(user.preferences?.workspace_chat ?? {}),
          ...preference,
        },
      }
      updateCurrentUserPreferences.mutate(preferences, {
        onSuccess: (nextUser) => useAuthStore.getState().setUser(nextUser),
      })
    },
    [updateCurrentUserPreferences, user],
  )

  useEffect(() => {
    if (!canPeerTab && conversationScope === 'peers') {
      setConversationScope('my')
    }
  }, [canPeerTab, conversationScope])

  useEffect(() => {
    if (!canOfflineMessages && workspaceChatTab === 'offline') {
      setWorkspaceChatTab('messages')
    }
  }, [canOfflineMessages, workspaceChatTab])

  useEffect(() => {
    if (!canQueueTab && workspaceChatTab === 'queue') {
      setWorkspaceChatTab('messages')
      setSelectedQueueTaskId(null)
    }
  }, [canQueueTab, workspaceChatTab])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const tab = new URLSearchParams(window.location.search).get('tab')
    const myView = new URLSearchParams(window.location.search).get('my_view')
    if (tab === 'queue' && canQueueTab) {
      setWorkspaceChatTab('queue')
    } else if (tab === 'offline' && canOfflineMessages) {
      setWorkspaceChatTab('offline')
    } else if (tab === 'peers' && canPeerTab) {
      setConversationScope('peers')
      setWorkspaceChatTab('messages')
    } else if (tab === 'my' || myView === 'history') {
      setConversationScope('my')
      setWorkspaceChatTab('messages')
      setMyConversationView(myView === 'history' ? 'history' : 'current')
    }
  }, [canOfflineMessages, canPeerTab, canQueueTab])

  useEffect(() => {
    if (!canOfflineMessages) {
      setSelectedOfflineMessageId(null)
      return
    }
    if (!isOfflineTabActive) return
    if (
      selectedOfflineMessageId
      && offlineMessageItems.some((item) => item.id === selectedOfflineMessageId)
    ) {
      return
    }
    if (skipOfflineAutoSelectRef.current) {
      skipOfflineAutoSelectRef.current = false
      return
    }
    setSelectedOfflineMessageId(offlineMessageItems[0]?.id ?? null)
  }, [canOfflineMessages, isOfflineTabActive, offlineMessageItems, selectedOfflineMessageId])

  useEffect(() => {
    if (!canQueueTab) {
      setSelectedQueueTaskId(null)
      return
    }
    if (!isQueueTabActive) return
    if (selectedQueueTaskId && queueTaskItems.some((item) => item.id === selectedQueueTaskId)) {
      return
    }
    if (skipQueueAutoSelectRef.current) {
      skipQueueAutoSelectRef.current = false
      return
    }
    setSelectedQueueTaskId(queueTaskItems[0]?.id ?? null)
  }, [canQueueTab, isQueueTabActive, queueTaskItems, selectedQueueTaskId])

  // Connect Socket.IO on mount
  useEffect(() => {
    if (token && !connected && !connecting && !authFailed) {
      connect(token)
    }
  }, [token, connected, connecting, authFailed, connect])

  // When the user switches back to this tab after it was backgrounded (and
  // possibly frozen by the browser), check if the socket silently died and
  // force an immediate reconnect + data refresh so the agent state is current
  // within a single frame rather than waiting for the next reconnection tick.
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const state = useSocketStore.getState()
        if (state.authFailed) return
        if (state.socket && !state.socket.connected) {
          state.socket.connect()
        }
        queryClient.invalidateQueries({ queryKey: agentKeys.status })
        queryClient.invalidateQueries({ queryKey: agentKeys.stats })
        queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
        if (canQueueTab) {
          queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.counts() })
          if (isQueueTabActive) {
            queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.lists() })
          }
        }
        if (canOfflineMessages) {
          queryClient.invalidateQueries({ queryKey: offlineMessageKeys.counts() })
          if (isOfflineTabActive) {
            queryClient.invalidateQueries({ queryKey: offlineMessageKeys.lists() })
          }
        }
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [canOfflineMessages, canQueueTab, isOfflineTabActive, isQueueTabActive, queryClient])

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
      if (canQueueTab) {
        queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.counts() })
        if (isQueueTabActive) {
          queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.lists() })
        }
      }
      if (canOfflineMessages) {
        queryClient.invalidateQueries({ queryKey: offlineMessageKeys.counts() })
        if (isOfflineTabActive) {
          queryClient.invalidateQueries({ queryKey: offlineMessageKeys.lists() })
        }
      }
    }
    socket.on('connect', handleConnect)
    return () => {
      socket.off('connect', handleConnect)
    }
  }, [socket, canOfflineMessages, canQueueTab, isOfflineTabActive, isQueueTabActive, queryClient])

  useEffect(() => {
    if (!socket || !connected) return

    const resources: Array<'queue' | 'offline'> = []
    if (canQueueTab) resources.push('queue')
    if (canOfflineMessages) resources.push('offline')
    if (resources.length === 0) return

    socket.emit('subscribe_workspace_counters', { resources })

    return () => {
      if (socket.connected) {
        socket.emit('unsubscribe_workspace_counters', { resources })
      }
    }
  }, [socket, connected, canOfflineMessages, canQueueTab])

  const activeWorkspaceRealtimeTab = useMemo<'queue' | 'offline' | 'peers' | null>(() => {
    if (canQueueTab && isQueueTabActive) return 'queue'
    if (canOfflineMessages && isOfflineTabActive) return 'offline'
    if (canPeerTab && isPeerTabActive) return 'peers'
    return null
  }, [canOfflineMessages, canPeerTab, canQueueTab, isOfflineTabActive, isPeerTabActive, isQueueTabActive])

  useEffect(() => {
    if (!socket || !connected || !activeWorkspaceRealtimeTab) return

    socket.emit('subscribe_workspace_tab', { tab: activeWorkspaceRealtimeTab })

    return () => {
      if (socket.connected) {
        socket.emit('unsubscribe_workspace_tab', { tab: activeWorkspaceRealtimeTab })
      }
    }
  }, [socket, connected, activeWorkspaceRealtimeTab])

  // Socket.IO event listeners
  useEffect(() => {
    if (!socket) return

    const handleNewConversation = (data: { conversation_id: number; visitor: Conversation['visitor'] }) => {
      playSessionAlert()
      const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'
      fetch(`${apiBase}v1/conversations/${data.conversation_id}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((r) => r.json())
        .then((conv: Conversation) => {
          queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
          if (canQueueTab) {
            queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.counts() })
            if (isQueueTabActive) {
              queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.lists() })
            }
          }
          if (conversationScope === 'my') addConversation(conv)
        })
        .catch(() => {})
    }

    const handleNewMessage = (msg: Message) => {
      // Peer conversations belong to a colleague: they must not raise an unread
      // badge or play the notification sound for the current agent.
      const isPeerMessage = msg.conversation_id === selectedPeerConversationIdRef.current
      if (msg.sender_type === 'visitor') {
        if (!isPeerMessage) {
          playMessageAlert()
        }
        setVisitorTyping(msg.conversation_id, false)
      }
      addMessage(msg.conversation_id, msg)
      const preview = buildMessagePreview(msg, locale)
      const previewSlice = preview.slice(0, 200)
      const baseUpdates: Partial<Conversation> = {
        last_message_at: msg.created_at,
        last_message_preview: previewSlice,
      }
      updateConversation(msg.conversation_id, baseUpdates)
      if (canQueueTab && isQueueTabActive) {
        queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.lists() })
      }
      // Increment unread if not the selected conversation
      const selected = useChatStore.getState().selectedConversationId
      let nextUnread: number | undefined
      if (!isPeerMessage && msg.sender_type === 'visitor') {
        if (msg.conversation_id === selected) {
          socket.emit('mark_read', { conversation_id: msg.conversation_id })
          markConversationRead(msg.conversation_id)
          nextUnread = 0
        } else {
          const conv = useChatStore.getState().conversations.find((c) => c.id === msg.conversation_id)
          if (conv) {
            nextUnread = conv.unread_count + 1
            updateConversation(msg.conversation_id, { unread_count: nextUnread })
          }
        }
      }
      patchConversationListCache(queryClient, msg.conversation_id, {
        ...baseUpdates,
        ...(nextUnread !== undefined ? { unread_count: nextUnread } : {}),
      })
    }

    const handleSatisfactionEvent = (data: { message?: Message; conversation_id: number }) => {
      if (data.message) {
        addMessage(data.conversation_id, data.message)
      }
      queryClient.invalidateQueries({
        queryKey: ['satisfaction-survey', 'conversation', data.conversation_id],
      })
    }

    const handleConversationEnded = (data: { conversation_id: number }) => {
      removeConversation(data.conversation_id)
      queryClient.invalidateQueries({ queryKey: conversationKeys.historyLists() })
    }

    const handleAgentStatsUpdated = (data: AgentStats) => {
      queryClient.setQueryData(agentKeys.stats, data)
    }

    const handleOfflineCountUpdated = () => {
      if (!canOfflineMessages) return
      queryClient.invalidateQueries({ queryKey: offlineMessageKeys.counts() })
    }

    const handleOfflineListUpdated = (data?: OfflineMessageUpdatedEvent) => {
      if (!canOfflineMessages) return
      const offlineMessageId = data?.offline_message_id
      if (data?.action === 'converted' && typeof offlineMessageId === 'number') {
        setSelectedOfflineMessageId((current) => {
          if (current !== offlineMessageId) return current
          const pendingItems = offlineMessageItems.some((item) => item.id === offlineMessageId)
            ? offlineMessageItems
            : queryClient.getQueryData<OfflineMessageListResponse>(
                offlineMessageKeys.list('pending'),
              )?.items ?? offlineMessageItems
          const nextId = getNextPendingOfflineMessageId(pendingItems, offlineMessageId)
          skipOfflineAutoSelectRef.current = nextId == null
          return nextId
        })
        removePendingOfflineMessageFromListCache(queryClient, offlineMessageId)
      }
      if (isOfflineTabActive) {
        queryClient.invalidateQueries({ queryKey: offlineMessageKeys.lists() })
      }
      if (typeof offlineMessageId === 'number') {
        queryClient.invalidateQueries({ queryKey: offlineMessageKeys.detail(offlineMessageId) })
      }
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
        playSessionAlert()
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

    const handleVisitorTyping = (data: { conversation_id: number; content?: string }) => {
      const content = data.content
      const hasContent = typeof content === 'string'
      if (hasContent && content.trim().length === 0) {
        setVisitorTyping(data.conversation_id, false)
        const staleTimer = typingTimerRef.current.get(data.conversation_id)
        if (staleTimer) clearTimeout(staleTimer)
        typingTimerRef.current.delete(data.conversation_id)
        return
      }

      setVisitorTyping(data.conversation_id, true, hasContent ? content : undefined)
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
      if (canQueueTab && isQueueTabActive) {
        queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.lists() })
      }
    }

    const handleQueueCountUpdated = () => {
      if (!canQueueTab) return
      queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.counts() })
    }

    const handleQueueListUpdated = (data?: QueueUpdatedEvent) => {
      if (!canQueueTab) return
      if (!isQueueTabActive) return

      queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.lists() })
      if (
        selectedQueueTaskId !== null
        && (typeof data?.task_id !== 'number' || data.task_id === selectedQueueTaskId)
      ) {
        queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.detail(selectedQueueTaskId) })
      }
      queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
      queryClient.invalidateQueries({ queryKey: agentKeys.stats })
    }

    const handleConversationListUpdated = (_data?: ConversationListUpdatedEvent) => {
      if (!canPeerTab || !isPeerTabActive) return
      queryClient.invalidateQueries({ queryKey: conversationKeys.list('peers') })
    }

    socket.on('new_conversation', handleNewConversation)
    socket.on('new_message', handleNewMessage)
    socket.on('conversation_ended', handleConversationEnded)
    socket.on('conversation_transferred', handleConversationTransferred)
    socket.on('visitor_typing', handleVisitorTyping)
    socket.on('conversation_updated', handleConversationUpdated)
    socket.on('queue_count_updated', handleQueueCountUpdated)
    socket.on('queue_list_updated', handleQueueListUpdated)
    socket.on('conversation_list_updated', handleConversationListUpdated)
    socket.on('agent_stats_updated', handleAgentStatsUpdated)
    socket.on('offline_count_updated', handleOfflineCountUpdated)
    socket.on('offline_list_updated', handleOfflineListUpdated)
    socket.on('satisfaction_invitation_sent', handleSatisfactionEvent)
    socket.on('satisfaction_feedback_submitted', handleSatisfactionEvent)

    return () => {
      socket.off('new_conversation', handleNewConversation)
      socket.off('new_message', handleNewMessage)
      socket.off('conversation_ended', handleConversationEnded)
      socket.off('conversation_transferred', handleConversationTransferred)
      socket.off('visitor_typing', handleVisitorTyping)
      socket.off('conversation_updated', handleConversationUpdated)
      socket.off('queue_count_updated', handleQueueCountUpdated)
      socket.off('queue_list_updated', handleQueueListUpdated)
      socket.off('conversation_list_updated', handleConversationListUpdated)
      socket.off('agent_stats_updated', handleAgentStatsUpdated)
      socket.off('offline_count_updated', handleOfflineCountUpdated)
      socket.off('offline_list_updated', handleOfflineListUpdated)
      socket.off('satisfaction_invitation_sent', handleSatisfactionEvent)
      socket.off('satisfaction_feedback_submitted', handleSatisfactionEvent)
    }
  }, [socket, token, queryClient, addConversation, addMessage, updateConversation, removeConversation, setVisitorTyping, markConversationRead, playMessageAlert, playSessionAlert, conversationScope, locale, canOfflineMessages, canPeerTab, canQueueTab, isOfflineTabActive, isPeerTabActive, isQueueTabActive, selectedQueueTaskId])

  const listSelectedConversation = conversations.find((c) => c.id === selectedConversationId) || null
  const selectedConversation =
    listSelectedConversation
    || (selectedConversationSnapshot?.id === selectedConversationId ? selectedConversationSnapshot : null)
  const selectedPeerConversationId = useMemo(() => {
    if (workspaceChatTab !== 'messages') return null
    if (!selectedConversation) return null
    if (selectedConversation.viewer_relation === 'peer') return selectedConversation.id
    if (
      selectedConversation.agent?.id != null
      && user?.id != null
      && selectedConversation.agent.id !== user.id
    ) {
      return selectedConversation.id
    }
    return null
  }, [selectedConversation, user?.id, workspaceChatTab])

  useEffect(() => {
    selectedPeerConversationIdRef.current = selectedPeerConversationId
  }, [selectedPeerConversationId])

  useEffect(() => {
    if (listSelectedConversation) {
      setSelectedConversationSnapshot(listSelectedConversation)
    } else if (selectedConversationId == null) {
      setSelectedConversationSnapshot(null)
    }
  }, [listSelectedConversation, selectedConversationId])

  useEffect(() => {
    if (!socket || !connected || !selectedPeerConversationId) return

    socket.emit('join_conversation', { conversation_id: selectedPeerConversationId })

    return () => {
      if (socket.connected) {
        socket.emit('leave_conversation', { conversation_id: selectedPeerConversationId })
      }
    }
  }, [socket, connected, selectedPeerConversationId])

  const getMaxAuxiliaryPanelWidth = useCallback(() => {
    const containerWidth = chatShellRef.current?.clientWidth
    if (!containerWidth) return AUXILIARY_PANEL_MAX_WIDTH

    const availableWidth = containerWidth - CONVERSATION_LIST_PANEL_WIDTH - MESSAGE_PANEL_MIN_WIDTH - RESIZE_HANDLE_WIDTH
    return Math.max(AUXILIARY_PANEL_MIN_WIDTH, Math.min(AUXILIARY_PANEL_MAX_WIDTH, availableWidth))
  }, [])

  useEffect(() => {
    const storedWidth = workspaceChatPreferences?.auxiliary_panel_width
    if (typeof storedWidth !== 'number') return
    setAuxiliaryPanelWidth(clampAuxiliaryPanelWidth(storedWidth, getMaxAuxiliaryPanelWidth()))
  }, [getMaxAuxiliaryPanelWidth, workspaceChatPreferences?.auxiliary_panel_width])

  const handleAuxiliaryPanelResizeStart = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (event.button !== 0) return

      event.preventDefault()
      const startX = event.clientX
      const startWidth = auxiliaryPanelWidth
      let nextWidth = startWidth

      setAuxiliaryPanelResizing(true)

      const handlePointerMove = (moveEvent: PointerEvent) => {
        moveEvent.preventDefault()
        nextWidth = clampAuxiliaryPanelWidth(startWidth + startX - moveEvent.clientX, getMaxAuxiliaryPanelWidth())
        setAuxiliaryPanelWidth(nextWidth)
      }

      const stopResize = () => {
        setAuxiliaryPanelResizing(false)
        saveWorkspaceChatPreference({ auxiliary_panel_width: nextWidth })
        window.removeEventListener('pointermove', handlePointerMove)
        window.removeEventListener('pointerup', stopResize)
        window.removeEventListener('pointercancel', stopResize)
      }

      window.addEventListener('pointermove', handlePointerMove)
      window.addEventListener('pointerup', stopResize)
      window.addEventListener('pointercancel', stopResize)
    },
    [auxiliaryPanelWidth, getMaxAuxiliaryPanelWidth, saveWorkspaceChatPreference],
  )

  const handleAuxiliaryPanelResizeKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (event.key === 'ArrowLeft') {
        event.preventDefault()
        setAuxiliaryPanelWidth((width) => {
          const nextWidth = clampAuxiliaryPanelWidth(width + 20, getMaxAuxiliaryPanelWidth())
          saveWorkspaceChatPreference({ auxiliary_panel_width: nextWidth })
          return nextWidth
        })
      } else if (event.key === 'ArrowRight') {
        event.preventDefault()
        setAuxiliaryPanelWidth((width) => {
          const nextWidth = clampAuxiliaryPanelWidth(width - 20, getMaxAuxiliaryPanelWidth())
          saveWorkspaceChatPreference({ auxiliary_panel_width: nextWidth })
          return nextWidth
        })
      } else if (event.key === 'Home') {
        event.preventDefault()
        setAuxiliaryPanelWidth(AUXILIARY_PANEL_MIN_WIDTH)
        saveWorkspaceChatPreference({ auxiliary_panel_width: AUXILIARY_PANEL_MIN_WIDTH })
      } else if (event.key === 'End') {
        event.preventDefault()
        const nextWidth = getMaxAuxiliaryPanelWidth()
        setAuxiliaryPanelWidth(nextWidth)
        saveWorkspaceChatPreference({ auxiliary_panel_width: nextWidth })
      }
    },
    [getMaxAuxiliaryPanelWidth, saveWorkspaceChatPreference],
  )

  useEffect(() => {
    const handleWindowResize = () => {
      setAuxiliaryPanelWidth((width) => clampAuxiliaryPanelWidth(width, getMaxAuxiliaryPanelWidth()))
    }

    window.addEventListener('resize', handleWindowResize)
    handleWindowResize()

    return () => window.removeEventListener('resize', handleWindowResize)
  }, [getMaxAuxiliaryPanelWidth])

  useEffect(() => {
    if (!auxiliaryPanelResizing) return

    const previousCursor = document.body.style.cursor
    const previousUserSelect = document.body.style.userSelect
    document.body.style.cursor = 'col-resize'
    document.body.style.userSelect = 'none'

    return () => {
      document.body.style.cursor = previousCursor
      document.body.style.userSelect = previousUserSelect
    }
  }, [auxiliaryPanelResizing])

  const handleKnowledgeUse = useCallback((messageText: string) => {
    setComposerInsertRequest((prev) => ({
      id: (prev?.id ?? 0) + 1,
      text: messageText,
    }))
  }, [])

  const visibleConversationItems = isMyHistoryActive ? historyConversations : conversations

  const handleConversationSelect = useCallback(
    (conversationId: number) => {
      const snapshot = visibleConversationItems.find((item) => item.id === conversationId)
      if (snapshot) setSelectedConversationSnapshot(snapshot)
      selectConversation(conversationId)
    },
    [selectConversation, visibleConversationItems],
  )

  const showWorkspaceToast = useCallback((text: string) => {
    setTransferToast(text)
    if (transferToastTimerRef.current) clearTimeout(transferToastTimerRef.current)
    transferToastTimerRef.current = setTimeout(() => setTransferToast(null), 2500)
  }, [])

  const handleOpenMessageSearch = useCallback(() => {
    if (!selectedConversation?.visitor) return
    setMessageSearchOpen(true)
  }, [selectedConversation?.visitor])

  useEffect(() => {
    if (!selectedConversation?.visitor && messageSearchOpen) {
      setMessageSearchOpen(false)
    }
  }, [messageSearchOpen, selectedConversation?.id, selectedConversation?.visitor])

  const handleKnowledgeSend = useCallback(
    (messageText: string) => {
      if (!socket || !connected || !selectedConversation || selectedConversation.status === 'closed') {
        throw new Error('Knowledge message cannot be sent')
      }
      const isPeerConversation =
        selectedConversation.viewer_relation === 'peer'
        || (
          selectedConversation.agent?.id != null
          && user?.id != null
          && selectedConversation.agent.id !== user.id
        )
      if (isPeerConversation && !hasPermission(user, 'chat.conversation.peer_message.send')) {
        throw new Error('No permission to send peer conversation message')
      }
      socket.emit('send_message', {
        conversation_id: selectedConversation.id,
        content: messageText,
        content_type: 'text',
      })
    },
    [connected, selectedConversation, socket, user],
  )

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

  const handleStartNewConversation = useCallback(
    async (conversationId: number) => {
      try {
        const result = await startConversationFromHistory.mutateAsync(conversationId)
        const conversation = result.conversation
        addConversation(conversation)
        setSelectedConversationSnapshot(conversation)
        selectConversation(conversation.id)
        setConversationScope('my')
        setMyConversationView('current')
        setWorkspaceChatTab('messages')
        queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
        queryClient.invalidateQueries({ queryKey: agentKeys.stats })
        showWorkspaceToast(
          result.already_active
            ? t('ws.chat.visitorHasActiveConversation', locale)
            : t('ws.chat.newConversationStarted', locale),
        )
      } catch {
        window.alert(t('ws.chat.startNewConversationFailed', locale))
      }
    },
    [
      addConversation,
      locale,
      queryClient,
      selectConversation,
      showWorkspaceToast,
      startConversationFromHistory,
    ],
  )

  const advanceOfflineMessageSelection = useCallback((convertedId: number) => {
    const nextId = getNextPendingOfflineMessageId(offlineMessageItems, convertedId)
    skipOfflineAutoSelectRef.current = nextId == null
    setSelectedOfflineMessageId(nextId)
  }, [offlineMessageItems])

  const handleOfflineAssigned = useCallback(
    (response: OfflineMessageConvertResponse, offlineMessageId: number) => {
      queryClient.invalidateQueries({ queryKey: offlineMessageKeys.counts() })
      if (response.assigned_to_current_user) {
        addConversation(response.conversation)
        advanceOfflineMessageSelection(offlineMessageId)
        queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
        queryClient.invalidateQueries({ queryKey: agentKeys.stats })
        return
      }
      advanceOfflineMessageSelection(offlineMessageId)
      void offlineMessagesQuery.refetch()
    },
    [addConversation, advanceOfflineMessageSelection, offlineMessagesQuery, queryClient],
  )

  const handleConversationPanelTabChange = useCallback((tab: ConversationPanelTab) => {
    if (tab === 'offline') {
      queryClient.invalidateQueries({ queryKey: offlineMessageKeys.lists() })
      setWorkspaceChatTab('offline')
      return
    }
    if (tab === 'queue') {
      queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.lists() })
      setWorkspaceChatTab('queue')
      return
    }
    setConversationScope(tab)
    setWorkspaceChatTab('messages')
  }, [queryClient])

  const handleMyConversationViewChange = useCallback((view: MyConversationView) => {
    setConversationScope('my')
    setWorkspaceChatTab('messages')
    setMyConversationView(view)
  }, [])

  const activeConversationPanelTab: ConversationPanelTab = workspaceChatTab === 'offline'
    ? 'offline'
    : workspaceChatTab === 'queue'
      ? 'queue'
    : conversationScope
  const offlineTotal = offlineMessageCountQuery.data?.total
    ?? (isOfflineTabActive ? offlineMessagesQuery.data?.total ?? offlineMessageItems.length : 0)
  const queueTotal = queueTaskCountQuery.data?.total
    ?? (isQueueTabActive ? queueTasksQuery.data?.total ?? queueTaskItems.length : 0)

  const advanceQueueTaskSelection = useCallback((assignedTaskId: number) => {
    const nextId = getNextQueueTaskId(queueTaskItems, assignedTaskId)
    skipQueueAutoSelectRef.current = nextId == null
    setSelectedQueueTaskId(nextId)
  }, [queueTaskItems])

  const handleQueueAssigned = useCallback(
    async (response: QueueAssignmentWorkspaceResponse) => {
      queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.counts() })
      queryClient.invalidateQueries({ queryKey: queueWorkspaceKeys.lists() })
      queryClient.invalidateQueries({ queryKey: conversationKeys.lists() })
      queryClient.invalidateQueries({ queryKey: agentKeys.stats })
      if (response.assigned_to_current_user && response.conversation_id) {
        try {
          const conversation = await get<Conversation>(`v1/conversations/${response.conversation_id}`)
          addConversation(conversation)
        } catch {
          // Keep processing the queue list even if conversation fetch fails.
        }
        advanceQueueTaskSelection(response.task.id)
        return
      }
      setSelectedQueueTaskId((current) => (current === response.task.id ? null : current))
      void queueTasksQuery.refetch()
    },
    [addConversation, advanceQueueTaskSelection, queryClient, queueTasksQuery],
  )

  const auxiliaryPanelResizeHandle = (
    <div
      role="separator"
      aria-label={locale === 'zh' ? '调整辅助区宽度' : 'Resize auxiliary panel'}
      aria-orientation="vertical"
      aria-valuemin={AUXILIARY_PANEL_MIN_WIDTH}
      aria-valuemax={AUXILIARY_PANEL_MAX_WIDTH}
      aria-valuenow={auxiliaryPanelWidth}
      tabIndex={0}
      onPointerDown={handleAuxiliaryPanelResizeStart}
      onKeyDown={handleAuxiliaryPanelResizeKeyDown}
      className={cn(
        'group relative z-10 w-px shrink-0 cursor-col-resize touch-none bg-transparent outline-none',
        auxiliaryPanelResizing && 'cursor-col-resize',
      )}
    >
      <div
        aria-hidden="true"
        className="absolute inset-y-0 left-1/2 w-3 -translate-x-1/2"
      />
      <div
        aria-hidden="true"
        className={cn(
          'pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-[#E5E5E5] transition-colors group-hover:bg-[#999999] group-focus-visible:bg-[#999999]',
          auxiliaryPanelResizing && 'bg-primary',
        )}
      />
    </div>
  )

  return (
    <div
      ref={chatShellRef}
      className="relative flex h-full min-h-0 bg-white"
    >
      {/* Connection status bar */}
      {workspaceChatTab === 'messages' && !connected && (
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
        conversations={visibleConversationItems}
        selectedId={selectedConversationId}
        onSelect={handleConversationSelect}
        agentStatus={agentStatus || null}
        agentStats={agentStats || null}
        scope={conversationScope}
        onScopeChange={setConversationScope}
        myView={myConversationView}
        onMyViewChange={handleMyConversationViewChange}
        activeTab={activeConversationPanelTab}
        onTabChange={handleConversationPanelTabChange}
        canPeerTab={canPeerTab}
        canOfflineTab={canOfflineMessages}
        canQueueTab={canQueueTab}
        peerConversationScope={peerConversationScope}
        offlineTotal={offlineTotal}
        queueTotal={queueTotal}
        loading={
          workspaceChatTab === 'queue'
            ? queueTasksQuery.isFetching
            : isMyHistoryActive
              ? historyConversationsQuery.isFetching
              : activeConversationsQuery.isFetching
        }
        onRefresh={() => {
          if (workspaceChatTab === 'queue') {
            void queueTasksQuery.refetch()
            return
          }
          if (isMyHistoryActive) {
            void historyConversationsQuery.refetch()
            return
          }
          void activeConversationsQuery.refetch()
        }}
        historyHasMore={Boolean(historyConversationsQuery.hasNextPage)}
        historyLoadingMore={historyConversationsQuery.isFetchingNextPage}
        onHistoryLoadMore={() => {
          if (historyConversationsQuery.hasNextPage && !historyConversationsQuery.isFetchingNextPage) {
            void historyConversationsQuery.fetchNextPage()
          }
        }}
        offlineList={(
          <OfflineMessageListSidebar
            status="pending"
            items={offlineMessageItems}
            selectedId={selectedOfflineMessageId}
            onSelect={setSelectedOfflineMessageId}
            loading={offlineMessagesQuery.isLoading}
            onRefresh={() => void offlineMessagesQuery.refetch()}
            showTitle={false}
          />
        )}
        queueList={(
          <QueueTaskListSidebar
            items={queueTaskItems}
            visibleQueues={queueTasksQuery.data?.visible_queues ?? []}
            selectedId={selectedQueueTaskId}
            loading={queueTasksQuery.isLoading || queueTasksQuery.isFetching}
            queueFilter={queueFilter}
            onQueueFilterChange={setQueueFilter}
            onSelect={setSelectedQueueTaskId}
            onRefresh={() => void queueTasksQuery.refetch()}
          />
        )}
      />

      {workspaceChatTab === 'messages' ? (
        <>
          {/* Message Panel */}
          <MessagePanel
            conversation={selectedConversation}
            socket={socket}
            connected={connected}
            agentStatus={agentStatus || null}
            onCreateTicket={openTicketDraft}
            onStartNewConversation={handleStartNewConversation}
            startingNewConversation={startConversationFromHistory.isPending}
            onTransferred={handleTransferred}
            composerInsertRequest={composerInsertRequest}
            composerInputHeight={workspaceChatPreferences?.composer_input_height}
            onComposerInputHeightCommit={(height) => saveWorkspaceChatPreference({ composer_input_height: height })}
            messageSearchOpen={messageSearchOpen}
            onOpenMessageSearch={handleOpenMessageSearch}
          />

          {auxiliaryPanelResizeHandle}

          {/* Auxiliary Panel */}
          {messageSearchOpen ? (
            <MessageSearchPanel
              conversation={selectedConversation}
              width={auxiliaryPanelWidth}
              onClose={() => setMessageSearchOpen(false)}
            />
          ) : (
            <AuxiliaryPanel
              conversation={selectedConversation}
              connected={connected}
              width={auxiliaryPanelWidth}
              ticketDraftOpen={selectedConversation ? ticketDraftConversationIds.has(selectedConversation.id) : false}
              onCloseTicketDraft={closeTicketDraft}
              onKnowledgeUse={handleKnowledgeUse}
              onKnowledgeSend={handleKnowledgeSend}
            />
          )}
        </>
      ) : workspaceChatTab === 'offline' ? (
        <OfflineMessageDetailPanel
          selectedId={selectedOfflineMessageId}
          onAssigned={handleOfflineAssigned}
          agentStatus={agentStatus || null}
          auxiliaryPanelWidth={auxiliaryPanelWidth}
          resizeHandle={auxiliaryPanelResizeHandle}
        />
      ) : (
        <QueueTaskPanel
          selectedId={selectedQueueTaskId}
          agentStatus={agentStatus || null}
          onAssigned={handleQueueAssigned}
        />
      )}
    </div>
  )
}
