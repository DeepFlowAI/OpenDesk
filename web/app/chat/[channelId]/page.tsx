'use client'

import { useEffect, useCallback, useMemo, useState, useRef } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import {
  createVisitorSession,
  fetchPublicMessages,
  fetchVisitorConversationHistory,
  useChannelPublic,
  type ChannelPublicConfig,
  type PublicMessage,
} from '@/service/use-visitor-chat'
import {
  createPublicSatisfactionInvitation,
  fetchPublicSatisfactionInvitation,
} from '@/service/use-satisfaction-survey'
import { useVisitorChatStore } from '@/context/visitor-chat-store'
import { VisitorChatRuntimeProvider } from '@/components/assistant-ui/visitor-chat-runtime'
import { VisitorThread } from '@/components/assistant-ui/visitor-thread'
import { ChatHeader } from '@/app/components/features/visitor-chat/chat-header'
import { LegalFooter } from '@/components/legal-footer'
import { IconLoader2, IconAlertTriangle } from '@tabler/icons-react'
import type { Locale } from '@/context/locale-store'
import type { Message, VisitorConversationHistoryItem } from '@/models/conversation'
import type { ChannelConfig } from '@/models/channel'
import { cn } from '@/lib/utils'

const HISTORY_PAGE_SIZE = 10
const HISTORY_CLIENT_LIMIT = 200

// ─── Utilities ───────────────────────────────────────────────────

type VisitorCredential = {
  visitorExternalId: string
  visitorSecret: string
  visitorSessionToken?: string
  visitorSessionExpiresAt?: number
  visitorPayloadKey?: string
}

type EmbedVisitorPayload = {
  name?: string
  metadata?: Record<string, unknown>
}

type EmbedInitPayload = {
  visitor?: EmbedVisitorPayload | null
}

const EMPTY_EMBED_INIT_PAYLOAD: EmbedInitPayload = {}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function sanitizeMetadata(value: unknown): Record<string, unknown> | null {
  if (!isPlainRecord(value)) return null
  try {
    const json = JSON.stringify(value)
    if (!json || json.length > 8192) return null
    const parsed = JSON.parse(json) as unknown
    return isPlainRecord(parsed) ? parsed : null
  } catch {
    return null
  }
}

function sanitizeEmbedVisitor(value: unknown): EmbedVisitorPayload | null {
  if (!isPlainRecord(value)) return null
  const visitor: EmbedVisitorPayload = {}
  if (typeof value.name === 'string') {
    const name = value.name.trim().slice(0, 64)
    if (name) visitor.name = name
  }
  const metadata = sanitizeMetadata(value.metadata)
  if (metadata) visitor.metadata = metadata
  return Object.keys(visitor).length > 0 ? visitor : null
}

function visitorCredentialStorageKey(channelKey: string): string {
  return `opendesk_visitor_${channelKey}`
}

function getVisitorPayloadKey(visitor?: EmbedVisitorPayload | null): string {
  return JSON.stringify(visitor || null)
}

function readVisitorCredential(channelKey: string): VisitorCredential | null {
  const key = visitorCredentialStorageKey(channelKey)
  const raw = localStorage.getItem(key)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<VisitorCredential>
    if (parsed.visitorExternalId && parsed.visitorSecret) {
      return {
        visitorExternalId: parsed.visitorExternalId,
        visitorSecret: parsed.visitorSecret,
        visitorSessionToken:
          typeof parsed.visitorSessionToken === 'string'
            ? parsed.visitorSessionToken
            : undefined,
        visitorSessionExpiresAt:
          typeof parsed.visitorSessionExpiresAt === 'number'
            ? parsed.visitorSessionExpiresAt
            : undefined,
        visitorPayloadKey:
          typeof parsed.visitorPayloadKey === 'string'
            ? parsed.visitorPayloadKey
            : undefined,
      }
    }
  } catch {
    // Older builds stored only the visitor_external_id string; it cannot be
    // safely renewed, so the next request will mint a fresh anonymous identity.
  }
  localStorage.removeItem(key)
  return null
}

function writeVisitorCredential(channelKey: string, credential: VisitorCredential) {
  localStorage.setItem(visitorCredentialStorageKey(channelKey), JSON.stringify(credential))
}

function clearVisitorCredential(channelKey: string) {
  localStorage.removeItem(visitorCredentialStorageKey(channelKey))
}

function mapPublicMessage(message: PublicMessage | Message): Message {
  return {
    ...message,
    conversation_id: 'conversation_id' in message && typeof message.conversation_id === 'number'
      ? message.conversation_id
      : 0,
  }
}

function mapPublicHistoryItem(item: VisitorConversationHistoryItem): VisitorConversationHistoryItem {
  return {
    ...item,
    messages: item.messages.map((message) => mapPublicMessage(message)),
  }
}

function getLocale(preferredLocale?: string | null): string {
  if (preferredLocale === 'zh' || preferredLocale === 'en') return preferredLocale
  if (typeof navigator === 'undefined') return 'en'
  const lang = navigator.language || 'en'
  return lang.startsWith('zh') ? 'zh' : 'en'
}

function postEmbedMessage(
  instanceId: string,
  message: { type: 'ready' | 'close' | 'error'; code?: string; message?: string },
) {
  if (typeof window === 'undefined' || !instanceId || window.parent === window) return
  window.parent.postMessage(
    {
      source: 'opendesk-chat',
      instanceId,
      ...message,
    },
    '*',
  )
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

function VisitorChatBootShell({
  channel,
  config,
  locale,
  isMobile,
  isEmbed,
  onEmbedClose,
}: {
  channel: ChannelPublicConfig
  config: ChannelConfig
  locale: string
  isMobile: boolean
  isEmbed: boolean
  onEmbedClose: () => void
}) {
  const placeholder =
    config.input_placeholder ||
    (locale === 'zh' ? '输入消息...' : 'Type a message...')

  return (
    <>
      <ChatHeader
        channel={channel}
        isMobile={isMobile}
        isEmbed={isEmbed}
        onEmbedClose={onEmbedClose}
      />
      <div
        className="flex flex-1 items-center justify-center"
        style={{
          backgroundColor:
            config.message_area_bg_color || 'var(--color-background)',
        }}
      >
        <IconLoader2 size={28} className="animate-spin text-muted-foreground" />
      </div>
      <div className="shrink-0 bg-background px-3 py-2 sm:px-4 sm:py-3">
        <div className="rounded-[14px] border border-border bg-background sm:rounded-2xl">
          <div className="flex min-h-[74px] items-start px-3 pt-2.5 text-sm text-[#9CA3AF] sm:px-4 sm:pt-3">
            {placeholder}
          </div>
          <div className="flex items-center justify-between px-2 pb-2 sm:px-3 sm:pb-2.5">
            <div className="h-8 w-8 rounded-md bg-muted/60" />
            <div className="h-8 w-8 rounded-full bg-[#F4F4F5]" />
          </div>
        </div>
      </div>
    </>
  )
}

// ─── Page ────────────────────────────────────────────────────────

export default function VisitorChatPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const channelKey = String(params.channelId ?? '')
  const isEmbed = searchParams.get('embed') === '1'
  const isPreload = isEmbed && searchParams.get('preload') === '1'
  const embedInstanceId = searchParams.get('opendesk_instance') || ''
  const embedInitRequired = isEmbed && Boolean(embedInstanceId)
  const embedActivationRequired = isPreload && Boolean(embedInstanceId)
  const preferredLocale = searchParams.get('locale')
  const locale = useMemo(
    () => getLocale(preferredLocale),
    [preferredLocale],
  )
  const isMobile = useIsMobile()
  const [visitorExternalId, setVisitorExternalId] = useState<string | null>(null)
  const [visitorSessionToken, setVisitorSessionToken] = useState<string | null>(null)

  const {
    socket,
    connected,
    connecting,
    conversationPublicId,
    messages,
    hasMore,
    satisfactionInvitation,
    connect,
    setConversationPublicId,
    setMessages,
    prependMessages,
    setHasMore,
    setSatisfactionInvitation,
  } = useVisitorChatStore()

  const {
    data: channel,
    error: channelError,
  } = useChannelPublic(channelKey, visitorExternalId, conversationPublicId)

  const [loadingMore, setLoadingMore] = useState(false)
  const [historyConversations, setHistoryConversations] = useState<VisitorConversationHistoryItem[]>([])
  const [historyHasMore, setHistoryHasMore] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [historyError, setHistoryError] = useState(false)
  const [historyLimitReached, setHistoryLimitReached] = useState(false)
  const [ended, setEnded] = useState(false)
  const [satisfactionCanInitiate, setSatisfactionCanInitiate] = useState(false)
  const [satisfactionLoading, setSatisfactionLoading] = useState(false)
  const [socketOfflineTitle, setSocketOfflineTitle] = useState('')
  const [socketOfflineMessage, setSocketOfflineMessage] = useState('')
  const [conversationInitializing, setConversationInitializing] = useState(true)
  const [embedReadyPosted, setEmbedReadyPosted] = useState(false)
  const [embedInitPayload, setEmbedInitPayload] = useState<EmbedInitPayload | null>(
    () => embedInitRequired ? null : EMPTY_EMBED_INIT_PAYLOAD,
  )
  const [embedActivated, setEmbedActivated] = useState(
    () => !embedActivationRequired,
  )
  const startedRef = useRef(false)
  // Offline UI is driven purely by the server's start_conversation response so
  // that a visitor with an unfinished conversation can always re-enter it,
  // regardless of whether any agent is currently online. The channel-level
  // availability hint is kept only as a fallback copy for the offline screen.
  const isOffline = !!socketOfflineMessage && !conversationPublicId

  const handleEmbedClose = useCallback(() => {
    postEmbedMessage(embedInstanceId, { type: 'close' })
  }, [embedInstanceId])

  useEffect(() => {
    setEmbedReadyPosted(false)
    setEmbedActivated(!embedActivationRequired)
    setEmbedInitPayload(embedInitRequired ? null : EMPTY_EMBED_INIT_PAYLOAD)
  }, [channelKey, embedActivationRequired, embedInstanceId, embedInitRequired])

  useEffect(() => {
    if (!embedInitRequired) return

    const handleMessage = (event: MessageEvent) => {
      if (event.source !== window.parent) return
      const data = event.data as unknown
      if (
        !isPlainRecord(data) ||
        data.source !== 'opendesk-sdk' ||
        (data.type !== 'init' && data.type !== 'open') ||
        data.instanceId !== embedInstanceId
      ) {
        return
      }

      setEmbedInitPayload((current) =>
        current ?? { visitor: sanitizeEmbedVisitor(data.visitor) },
      )
      if (data.type === 'open' || data.active === true || data.preload !== true) {
        setEmbedActivated(true)
      }
    }

    window.addEventListener('message', handleMessage)
    return () => {
      window.removeEventListener('message', handleMessage)
    }
  }, [embedInitRequired, embedInstanceId])

  useEffect(() => {
    if (!embedInitRequired || !embedReadyPosted || !embedActivated || embedInitPayload !== null) return
    const timer = window.setTimeout(() => {
      setEmbedInitPayload((current) => current ?? EMPTY_EMBED_INIT_PAYLOAD)
    }, 3000)
    return () => window.clearTimeout(timer)
  }, [embedActivated, embedInitPayload, embedInitRequired, embedReadyPosted])

  useEffect(() => {
    if (!isEmbed || !embedInstanceId || !channel || embedReadyPosted) return
    postEmbedMessage(embedInstanceId, { type: 'ready' })
    setEmbedReadyPosted(true)
  }, [channel, embedInstanceId, embedReadyPosted, isEmbed])

  useEffect(() => {
    if (!isEmbed || !embedInstanceId || !channelError) return
    postEmbedMessage(embedInstanceId, {
      type: 'error',
      code: 'CONFIG_LOAD_FAILED',
      message: 'Failed to load OpenDesk channel config.',
    })
  }, [channelError, embedInstanceId, isEmbed])

  useEffect(() => {
    let cancelled = false
    if (!channelKey || !embedActivated || (embedInitRequired && embedInitPayload === null)) return
    const embedVisitor = embedInitPayload?.visitor
    const visitorPayloadKey = getVisitorPayloadKey(embedVisitor)

    setVisitorExternalId(null)
    setVisitorSessionToken(null)
    setConversationPublicId(null)
    setMessages([])
    setHasMore(false)
    setSatisfactionInvitation(null)
    setSatisfactionCanInitiate(false)
    setEnded(false)
    setSocketOfflineTitle('')
    setSocketOfflineMessage('')
    setConversationInitializing(true)
    startedRef.current = false

    const createSession = async () => {
      const stored = readVisitorCredential(channelKey)
      const storedToken = stored?.visitorSessionToken
      const storedSessionExpiresAt = stored?.visitorSessionExpiresAt
      const reusableToken =
        storedToken &&
        typeof storedSessionExpiresAt === 'number' &&
        storedSessionExpiresAt > Date.now() + 60 * 1000 &&
        stored.visitorPayloadKey === visitorPayloadKey

      if (stored && reusableToken) {
        return {
          session: {
            visitor_external_id: stored.visitorExternalId,
            visitor_session_token: storedToken,
            visitor_secret: stored.visitorSecret,
            expires_in: Math.max(
              0,
              Math.floor((storedSessionExpiresAt - Date.now()) / 1000),
            ),
          },
          stored,
          reused: true,
        }
      }

      try {
        return {
          session: await createVisitorSession({
            channelKey,
            visitorExternalId: stored?.visitorExternalId,
            visitorSecret: stored?.visitorSecret,
            visitorName: embedVisitor?.name,
            metadata: embedVisitor?.metadata,
          }),
          stored,
          reused: false,
        }
      } catch (error) {
        if (!stored) throw error
        clearVisitorCredential(channelKey)
        return {
          session: await createVisitorSession({
            channelKey,
            visitorName: embedVisitor?.name,
            metadata: embedVisitor?.metadata,
          }),
          stored: null,
          reused: false,
        }
      }
    }

    createSession()
      .then(({ session, stored, reused }) => {
        if (cancelled) return
        const visitorSecret = session.visitor_secret || stored?.visitorSecret
        if (visitorSecret) {
          writeVisitorCredential(channelKey, {
            visitorExternalId: session.visitor_external_id,
            visitorSecret,
            visitorSessionToken: session.visitor_session_token,
            visitorSessionExpiresAt: reused
              ? stored?.visitorSessionExpiresAt
              : Date.now() + session.expires_in * 1000,
            visitorPayloadKey,
          })
        }
        setVisitorExternalId(session.visitor_external_id)
        setVisitorSessionToken(session.visitor_session_token)
      })
      .catch(() => {
        if (!cancelled) {
          setVisitorExternalId(null)
          setVisitorSessionToken(null)
        }
      })
    return () => {
      cancelled = true
    }
  }, [
    channelKey,
    embedActivated,
    embedInitPayload,
    embedInitRequired,
    setConversationPublicId,
    setHasMore,
    setMessages,
    setSatisfactionInvitation,
  ])

  const startConversation = useCallback(async () => {
    if (!socket || !connected || !visitorSessionToken) return

    if (!conversationPublicId && !socketOfflineMessage) {
      setConversationInitializing(true)
    }
    await new Promise<void>((resolve) => {
      let resolved = false
      const resolveOnce = () => {
        if (resolved) return
        resolved = true
        resolve()
      }
      const timer = window.setTimeout(() => {
        setConversationInitializing(false)
        resolveOnce()
      }, 30000)

      socket.emit(
        'start_conversation',
        {},
        async (res: {
          ok?: boolean
          conversation?: { conversation_public_id: string; status?: string }
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
            setConversationPublicId(res.conversation.conversation_public_id)
            setEnded(res.conversation.status === 'closed')
            try {
              const data = await fetchPublicMessages({
                conversationPublicId: res.conversation.conversation_public_id,
                visitorSessionToken,
                limit: 50,
              })
              setMessages(data.items.map(mapPublicMessage))
              setHasMore(data.has_more)
              fetchPublicSatisfactionInvitation({
                conversationPublicId: res.conversation.conversation_public_id,
                visitorSessionToken,
              })
                .then((satisfaction) => {
                  setSatisfactionInvitation(satisfaction.invitation)
                  setSatisfactionCanInitiate(satisfaction.can_initiate)
                })
                .catch(() => {
                  setSatisfactionInvitation(null)
                  setSatisfactionCanInitiate(false)
                })
            } catch {
              setMessages([])
              setHasMore(false)
              setSatisfactionCanInitiate(false)
            }
          } else if (res.error === 'OFFLINE') {
            setConversationPublicId(null)
            setMessages([])
            setHasMore(false)
            setSatisfactionInvitation(null)
            setSatisfactionCanInitiate(false)
            setEnded(false)
            setSocketOfflineTitle(res.offline_title || '')
            setSocketOfflineMessage(res.offline_message || '')
          }
          window.clearTimeout(timer)
          setConversationInitializing(false)
          resolveOnce()
        },
      )
    })
  }, [
    socket,
    connected,
    conversationPublicId,
    setConversationPublicId,
    setMessages,
    setHasMore,
    setSatisfactionInvitation,
    socketOfflineMessage,
    visitorSessionToken,
  ])

  const handleSatisfactionInitiate = useCallback(async () => {
    if (satisfactionInvitation) return satisfactionInvitation
    if (!conversationPublicId || !visitorSessionToken) return null

    setSatisfactionLoading(true)
    try {
      const state = await createPublicSatisfactionInvitation({
        conversationPublicId,
        visitorSessionToken,
      })
      setSatisfactionInvitation(state.invitation)
      setSatisfactionCanInitiate(state.can_initiate)
      return state.invitation
    } finally {
      setSatisfactionLoading(false)
    }
  }, [conversationPublicId, satisfactionInvitation, setSatisfactionInvitation, visitorSessionToken])

  const handleSatisfactionSubmitted = useCallback(() => {
    setSatisfactionCanInitiate(false)
  }, [])

  // ── Browser tab title & favicon (admin: document_title, favicon_url) ──
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
    if (!embedActivated || !channel || !visitorExternalId || !visitorSessionToken || connected || connecting) return
    connect(visitorSessionToken, visitorExternalId)
  }, [channel, connected, connecting, connect, embedActivated, visitorExternalId, visitorSessionToken])

  // ── Start conversation ──
  useEffect(() => {
    if (!embedActivated || !socket || !connected || startedRef.current) return
    startedRef.current = true
    void startConversation()
  }, [socket, connected, embedActivated, startConversation])

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
    const handler = () => {
      setEnded(true)
      if (!conversationPublicId || !visitorSessionToken) return

      setSatisfactionLoading(true)
      fetchPublicSatisfactionInvitation({
        conversationPublicId,
        visitorSessionToken,
      })
        .then((satisfaction) => {
          setSatisfactionInvitation(satisfaction.invitation)
          setSatisfactionCanInitiate(satisfaction.can_initiate)
        })
        .catch(() => {
          setSatisfactionCanInitiate(false)
        })
        .finally(() => {
          setSatisfactionLoading(false)
        })
    }
    socket.on('conversation_ended', handler)
    return () => {
      socket.off('conversation_ended', handler)
    }
  }, [conversationPublicId, setSatisfactionInvitation, socket, visitorSessionToken])

  // ── Typing emission ──
  const handleTyping = useCallback((content: string) => {
    if (!socket || !conversationPublicId) return
    socket.emit('typing', { conversation_public_id: conversationPublicId, content })
  }, [socket, conversationPublicId])

  // ── Load more messages ──
  const handleLoadMore = useCallback(async () => {
    if (!conversationPublicId || !visitorSessionToken || loadingMore || !hasMore) return
    const oldest = messages[0]
    if (!oldest) return
    setLoadingMore(true)
    try {
      const data = await fetchPublicMessages({
        conversationPublicId,
        visitorSessionToken,
        beforeId: oldest.id,
        limit: 20,
      })
      prependMessages(data.items.map(mapPublicMessage))
      setHasMore(data.has_more)
    } catch {
      // ignore
    } finally {
      setLoadingMore(false)
    }
  }, [conversationPublicId, visitorSessionToken, loadingMore, hasMore, messages, prependMessages, setHasMore])

  const handleLoadHistory = useCallback(
    async (beforeId?: string) => {
      if (!visitorSessionToken || historyLoading || historyLimitReached) return
      setHistoryLoading(true)
      setHistoryError(false)
      try {
        const data = await fetchVisitorConversationHistory({
          visitorSessionToken,
          currentConversationPublicId: conversationPublicId,
          beforePublicId: beforeId,
          limit: HISTORY_PAGE_SIZE,
        })
        const chronologicalItems = [...data.items].reverse().map(mapPublicHistoryItem)
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
      conversationPublicId,
      historyConversations.length,
      historyLimitReached,
      historyLoading,
      visitorSessionToken,
    ],
  )

  // ── Derived values ──
  const config = channel?.config || defaultConfig
  const pageBg = config.page_bg_color || 'var(--color-muted)'
  const offlineTitle = socketOfflineTitle || channel?.availability?.offline_title || config.offline_title
  const offlineMessage = socketOfflineMessage || channel?.availability?.offline_message || config.offline_message
  const showConnectionStatus = Boolean(socket) && !connected && !connecting && !isOffline

  const footerLocale: Locale = locale === 'zh' ? 'zh' : 'en'

  useEffect(() => {
    if (!isEmbed) return
    document.documentElement.classList.add('od-embed')
    return () => document.documentElement.classList.remove('od-embed')
  }, [isEmbed])

  const pageShellClassName = cn(
    'flex min-h-0 flex-col',
    isEmbed
      ? 'h-full overflow-hidden rounded-[14px] bg-background'
      : 'h-dvh',
  )
  const pageShellStyle = isEmbed ? undefined : { backgroundColor: pageBg }
  const chatContainerClassName = cn(
    'mx-auto flex w-full min-h-0 flex-1 flex-col',
    isEmbed
      ? 'min-w-0 max-w-none'
      : cn(
          'bg-background',
          isMobile ? '' : 'max-w-[720px] min-w-[480px] shadow-xl',
        ),
  )

  // ── Error state ──
  if (channelError && !channel) {
    return (
      <div
        className={pageShellClassName}
        style={pageShellStyle}
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

  // ── Loading state ──
  if (!channel || !visitorExternalId || !visitorSessionToken) {
    return (
      <div
        className={pageShellClassName}
        style={pageShellStyle}
      >
        <div className={chatContainerClassName}>
          {channel ? (
            <VisitorChatBootShell
              channel={channel}
              config={config}
              locale={locale}
              isMobile={isMobile}
              isEmbed={isEmbed}
              onEmbedClose={handleEmbedClose}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center">
              <IconLoader2 size={32} className="animate-spin text-muted-foreground" />
            </div>
          )}
        </div>
        <LegalFooter locale={footerLocale} compact />
      </div>
    )
  }

  if (!channel) {
    return (
      <div
        className={pageShellClassName}
        style={pageShellStyle}
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
    <div className={pageShellClassName} style={pageShellStyle}>
      {/* ── Connection status bar ── */}
      {showConnectionStatus && (
        <div className="absolute left-0 right-0 top-0 z-50 border-b border-amber-200/50 bg-[#f4ebd4] px-4 py-1 text-center text-xs text-stone-800">
          {locale === 'zh'
            ? '连接断开，正在重连...'
            : 'Connection lost, reconnecting...'}
        </div>
      )}

      {/* ── Chat container (backed by assistant-ui runtime) ── */}
      <div className={chatContainerClassName}>
        <VisitorChatRuntimeProvider
          socket={socket}
          channel={channel}
          config={config}
          locale={locale}
          isMobile={isMobile}
          ended={ended}
          conversationPublicId={conversationPublicId}
          visitorSessionToken={visitorSessionToken}
          hasMore={hasMore}
          loadingMore={loadingMore}
          historyAvailable={channel.has_conversation_history || historyConversations.length > 0}
          historyConversations={historyConversations}
          historyHasMore={historyHasMore}
          historyLoading={historyLoading}
          historyLoaded={historyLoaded}
          historyError={historyError}
          historyLimitReached={historyLimitReached}
          initializing={conversationInitializing}
          satisfactionCanInitiate={satisfactionCanInitiate}
          satisfactionLoading={satisfactionLoading}
          onLoadMore={handleLoadMore}
          onLoadHistory={handleLoadHistory}
          onTyping={handleTyping}
          onRestartConversation={startConversation}
          onSatisfactionInitiate={handleSatisfactionInitiate}
          onSatisfactionSubmitted={handleSatisfactionSubmitted}
        >
          <VisitorThread
            offlineTitle={isOffline ? offlineTitle : undefined}
            offlineMessage={isOffline ? offlineMessage : undefined}
            isEmbed={isEmbed}
            onEmbedClose={handleEmbedClose}
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
