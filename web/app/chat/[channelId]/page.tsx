'use client'

import { useEffect, useCallback, useMemo, useState, useRef } from 'react'
import { useParams } from 'next/navigation'
import { fetchVisitorConversationHistory, useChannelPublic } from '@/service/use-visitor-chat'
import { useVisitorChatStore } from '@/context/visitor-chat-store'
import { VisitorChatRuntimeProvider } from '@/components/assistant-ui/visitor-chat-runtime'
import { VisitorThread } from '@/components/assistant-ui/visitor-thread'
import { LegalFooter } from '@/components/legal-footer'
import { IconLoader2, IconAlertTriangle } from '@tabler/icons-react'
import type { Locale } from '@/context/locale-store'
import type { Message, VisitorConversationHistoryItem } from '@/models/conversation'
import type { ChannelConfig } from '@/models/channel'
import ky from 'ky'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'
const publicClient = ky.create({ prefixUrl: API_BASE, timeout: 30000 })
const HISTORY_PAGE_SIZE = 10
const HISTORY_CLIENT_LIMIT = 200

// ─── Utilities ───────────────────────────────────────────────────

function getVisitorId(channelId: number): string {
  const key = `opendesk_visitor_${channelId}`
  let id = localStorage.getItem(key)
  if (!id) {
    id = `v_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
    localStorage.setItem(key, id)
  }
  return id
}

function getLocale(): string {
  if (typeof navigator === 'undefined') return 'en'
  const lang = navigator.language || 'en'
  return lang.startsWith('zh') ? 'zh' : 'en'
}

function useIsMobile() {
  const [mobile, setMobile] = useState(false)
  useEffect(() => {
    const check = () => setMobile(window.innerWidth <= 768)
    check()
    window.addEventListener('resize', check)
    return () => window.removeEventListener('resize', check)
  }, [])
  return mobile
}

const defaultConfig: ChannelConfig = {
  title: null,
  document_title: null,
  page_bg_color: null,
  header_gradient_start: null,
  header_gradient_end: null,
  header_title_color: null,
  message_area_bg_color: null,
  agent_bubble_bg_color: null,
  agent_bubble_text_color: null,
  agent_bubble_border_color: null,
  agent_bubble_radius: [10, 10, 0, 10],
  use_agent_avatar: false,
  user_bubble_bg_color: null,
  user_bubble_text_color: null,
  user_bubble_border_color: null,
  user_bubble_radius: [10, 10, 10, 0],
  embed_button_bg_color: null,
  embed_button_icon_color: null,
  send_button_bg_color: null,
  input_placeholder: null,
  service_hours_enabled: false,
  service_hours_id: null,
  offline_title: '当前客服不在线',
  offline_message: '您好，当前客服不在线，您可以稍后再来咨询，我们会尽快为您服务。',
}

// ─── Page ────────────────────────────────────────────────────────

export default function VisitorChatPage() {
  const params = useParams()
  const channelId = Number(params.channelId)
  const locale = useMemo(getLocale, [])
  const isMobile = useIsMobile()
  const [visitorExternalId, setVisitorExternalId] = useState<string | null>(null)

  const {
    socket,
    connected,
    connecting,
    conversationId,
    messages,
    hasMore,
    connect,
    setConversationId,
    setMessages,
    prependMessages,
    setHasMore,
  } = useVisitorChatStore()

  const {
    data: channel,
    isLoading: channelLoading,
    error: channelError,
  } = useChannelPublic(channelId, visitorExternalId, conversationId)

  const [loadingMore, setLoadingMore] = useState(false)
  const [historyConversations, setHistoryConversations] = useState<VisitorConversationHistoryItem[]>([])
  const [historyHasMore, setHistoryHasMore] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [historyError, setHistoryError] = useState(false)
  const [historyLimitReached, setHistoryLimitReached] = useState(false)
  const [ended, setEnded] = useState(false)
  const [socketOfflineTitle, setSocketOfflineTitle] = useState('')
  const [socketOfflineMessage, setSocketOfflineMessage] = useState('')
  const startedRef = useRef(false)
  // Offline UI is driven purely by the server's start_conversation response so
  // that a visitor with an unfinished conversation can always re-enter it,
  // regardless of whether any agent is currently online. The channel-level
  // availability hint is kept only as a fallback copy for the offline screen.
  const isOffline = !!socketOfflineMessage && !conversationId

  useEffect(() => {
    if (!channelId) return
    setVisitorExternalId(getVisitorId(channelId))
  }, [channelId])

  const startConversation = useCallback(async () => {
    if (!socket || !connected) return

    await new Promise<void>((resolve) => {
      socket.emit(
        'start_conversation',
        { channel_id: channelId },
        async (res: {
          ok?: boolean
          conversation?: { id: number; status?: string }
          is_new?: boolean
          error?: string
          reason?: string
          offline_title?: string
          offline_message?: string
        }) => {
          if (res.ok && res.conversation) {
            // Clear stale offline copy after a successful new or resumed conversation.
            setSocketOfflineTitle('')
            setSocketOfflineMessage('')
            setConversationId(res.conversation.id)
            setEnded(res.conversation.status === 'closed')
            try {
              const data = await publicClient
                .get(`v1/public/conversations/${res.conversation.id}/messages`, {
                  searchParams: { limit: 50 },
                })
                .json<{ items: Message[]; has_more: boolean }>()
              setMessages(data.items)
              setHasMore(data.has_more)
            } catch {
              setMessages([])
              setHasMore(false)
            }
          } else if (res.error === 'OFFLINE') {
            setConversationId(null)
            setMessages([])
            setHasMore(false)
            setEnded(false)
            setSocketOfflineTitle(res.offline_title || '')
            setSocketOfflineMessage(res.offline_message || '')
          }
          resolve()
        },
      )
    })
  }, [socket, connected, channelId, setConversationId, setMessages, setHasMore])

  // ── Browser tab title & favicon (admin: 网页标题 document_title, 网页图标 favicon_url) ──
  useEffect(() => {
    if (!channel) return
    const c = channel.config
    document.title = c.document_title?.trim() || c.title?.trim() || channel.name

    const href = channel.favicon_url?.trim()
    const existing = document.querySelector<HTMLLinkElement>(
      "link[rel='icon'][data-opendesk-channel-favicon='true']",
    )
    if (href) {
      const link = existing ?? document.createElement('link')
      link.rel = 'icon'
      link.setAttribute('data-opendesk-channel-favicon', 'true')
      link.href = href
      if (!existing) document.head.appendChild(link)
    } else if (existing) {
      existing.remove()
    }
  }, [channel])

  // ── Socket connection ──
  // Always connect once we have the channel info. The server decides whether
  // the visitor is allowed in (existing conversation always wins, otherwise
  // start_conversation may return OFFLINE which we surface via isOffline).
  useEffect(() => {
    if (!channel || !visitorExternalId || connected || connecting) return
    connect(channel.tenant_id, visitorExternalId, channelId)
  }, [channel, channelId, connected, connecting, connect, visitorExternalId])

  // ── Start conversation ──
  useEffect(() => {
    if (!socket || !connected || startedRef.current) return
    startedRef.current = true
    void startConversation()
  }, [socket, connected, startConversation])

  useEffect(() => {
    if (!socket) return

    const handleDisconnect = () => {
      startedRef.current = false
    }

    socket.on('disconnect', handleDisconnect)
    return () => {
      socket.off('disconnect', handleDisconnect)
    }
  }, [socket])

  // ── Conversation ended listener ──
  useEffect(() => {
    if (!socket) return
    const handler = () => setEnded(true)
    socket.on('conversation_ended', handler)
    return () => {
      socket.off('conversation_ended', handler)
    }
  }, [socket])

  // ── Typing emission ──
  const handleTyping = useCallback((content: string) => {
    if (!socket || !conversationId) return
    socket.emit('typing', { conversation_id: conversationId, content })
  }, [socket, conversationId])

  // ── Load more messages ──
  const handleLoadMore = useCallback(async () => {
    if (!conversationId || loadingMore || !hasMore) return
    const oldest = messages[0]
    if (!oldest) return
    setLoadingMore(true)
    try {
      const data = await publicClient
        .get(`v1/public/conversations/${conversationId}/messages`, {
          searchParams: { before_id: oldest.id, limit: 20 },
        })
        .json<{ items: Message[]; has_more: boolean }>()
      prependMessages(data.items)
      setHasMore(data.has_more)
    } catch {
      // ignore
    } finally {
      setLoadingMore(false)
    }
  }, [conversationId, loadingMore, hasMore, messages, prependMessages, setHasMore])

  const handleLoadHistory = useCallback(
    async (beforeId?: number) => {
      if (!visitorExternalId || historyLoading || historyLimitReached) return
      setHistoryLoading(true)
      setHistoryError(false)
      try {
        const data = await fetchVisitorConversationHistory({
          channelId,
          visitorExternalId,
          currentConversationId: conversationId,
          beforeId,
          limit: HISTORY_PAGE_SIZE,
        })
        const chronologicalItems = [...data.items].reverse()
        setHistoryConversations((prev) =>
          beforeId ? [...chronologicalItems, ...prev] : chronologicalItems,
        )
        setHistoryHasMore(data.has_more)
        setHistoryLoaded(true)
        setHistoryLimitReached((prev) =>
          prev || historyConversations.length + chronologicalItems.length >= HISTORY_CLIENT_LIMIT,
        )
      } catch {
        setHistoryError(true)
      } finally {
        setHistoryLoading(false)
      }
    },
    [
      channelId,
      conversationId,
      historyConversations.length,
      historyLimitReached,
      historyLoading,
      visitorExternalId,
    ],
  )

  // ── Derived values ──
  const config = channel?.config || defaultConfig
  const pageBg = config.page_bg_color || 'var(--color-muted)'
  const offlineTitle = socketOfflineTitle || channel?.availability?.offline_title || config.offline_title
  const offlineMessage = socketOfflineMessage || channel?.availability?.offline_message || config.offline_message

  const footerLocale: Locale = locale === 'zh' ? 'zh' : 'en'

  // ── Loading state ──
  if (!visitorExternalId || channelLoading) {
    return (
      <div
        className="flex h-dvh flex-col"
        style={{ backgroundColor: pageBg }}
      >
        <div className="flex flex-1 items-center justify-center">
          <IconLoader2 size={32} className="animate-spin text-muted-foreground" />
        </div>
        <LegalFooter locale={footerLocale} compact />
      </div>
    )
  }

  // ── Error state ──
  if (channelError || !channel) {
    return (
      <div
        className="flex h-dvh flex-col"
        style={{ backgroundColor: pageBg }}
      >
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <IconAlertTriangle size={48} className="text-destructive" />
          <p className="text-sm text-muted-foreground">
            {locale === 'zh'
              ? '该对话链接无效或已失效'
              : 'This conversation link is invalid or expired'}
          </p>
        </div>
        <LegalFooter locale={footerLocale} compact />
      </div>
    )
  }

  return (
    <div className="flex h-dvh flex-col" style={{ backgroundColor: pageBg }}>
      {/* ── Connection status bar ── */}
      {!connected && !isOffline && (
        <div className="absolute left-0 right-0 top-0 z-50 border-b border-amber-200/50 bg-[#f4ebd4] px-4 py-1 text-center text-xs text-stone-800">
          {connecting
            ? locale === 'zh'
              ? '连接中...'
              : 'Connecting...'
            : locale === 'zh'
              ? '连接断开，正在重连...'
              : 'Connection lost, reconnecting...'}
        </div>
      )}

      {/* ── Chat container (backed by assistant-ui runtime) ── */}
      <div
        className={`mx-auto flex w-full min-h-0 flex-1 flex-col bg-background ${
          isMobile ? '' : 'max-w-[720px] min-w-[480px] shadow-xl'
        }`}
      >
        <VisitorChatRuntimeProvider
          socket={socket}
          channel={channel}
          config={config}
          locale={locale}
          isMobile={isMobile}
          ended={ended}
          conversationId={conversationId}
          hasMore={hasMore}
          loadingMore={loadingMore}
          historyAvailable={channel.has_conversation_history || historyConversations.length > 0}
          historyConversations={historyConversations}
          historyHasMore={historyHasMore}
          historyLoading={historyLoading}
          historyLoaded={historyLoaded}
          historyError={historyError}
          historyLimitReached={historyLimitReached}
          onLoadMore={handleLoadMore}
          onLoadHistory={handleLoadHistory}
          onTyping={handleTyping}
          onRestartConversation={startConversation}
        >
          <VisitorThread
            offlineTitle={isOffline ? offlineTitle : undefined}
            offlineMessage={isOffline ? offlineMessage : undefined}
          />
        </VisitorChatRuntimeProvider>
      </div>

      {/* AGPL §13: visitors interacting with this network service must be
          offered the Corresponding Source. Compact variant keeps the chat UX
          uncluttered on both mobile and desktop. */}
      <LegalFooter locale={footerLocale} compact />
    </div>
  )
}
