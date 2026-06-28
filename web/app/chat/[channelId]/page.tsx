'use client'

import { useEffect, useCallback, useMemo, useState, useRef } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import {
  createVisitorSession,
  fetchCurrentOfflineMessage,
  fetchPublicMessages,
  fetchOfflineMessages,
  fetchUnreadOfflineReplies,
  fetchVisitorConversationHistory,
  markConversationCustomerRead,
  syncConversationContext,
  useChannelPublic,
  type ChannelPublicConfig,
  type PublicMessage,
} from '@/service/use-visitor-chat'
import { telemetry } from '@/service/telemetry'
import {
  createPublicSatisfactionInvitation,
  fetchPublicSatisfactionInvitation,
} from '@/service/use-satisfaction-survey'
import { usePublicEmojiSettings } from '@/service/use-emoji-settings'
import type { HumanHandoffEventPayload } from '@/service/use-open-agent-conversation'
import { useVisitorChatStore } from '@/context/visitor-chat-store'
import { VisitorChatRuntimeProvider } from '@/components/assistant-ui/visitor-chat-runtime'
import { VisitorThread } from '@/components/assistant-ui/visitor-thread'
import { ChatHeader } from '@/app/components/features/visitor-chat/chat-header'
import { VisitorAssistPanel } from '@/app/components/features/visitor-chat/visitor-assist-panel'
import { LegalFooter } from '@/components/legal-footer'
import { IconLoader2, IconAlertTriangle } from '@tabler/icons-react'
import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type {
  Message,
  VisitorConversationHistoryItem,
  VisitorUnreadOfflineReplyItem,
} from '@/models/conversation'
import type { ChannelConfig } from '@/models/channel'
import { cn } from '@/lib/utils'
import { isVisitorQueueEnteredMessage } from '@/lib/visitor-queue-notice'

const HISTORY_PAGE_SIZE = 10
const HISTORY_CLIENT_LIMIT = 200
const READ_RECEIPT_ACK_TIMEOUT_MS = 5000
const READ_RECEIPT_RETRY_DELAY_MS = 1200

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
  customer?: Record<string, unknown>
  metadata?: Record<string, unknown>
}

type EmbedInitPayload = {
  visitor?: EmbedVisitorPayload | null
  contextToken?: string | null
  sessionSummary?: Record<string, unknown> | null
}

type SearchParamsReader = Pick<URLSearchParams, 'get' | 'has'>

type UserAgentBrand = {
  brand: string
  version: string
}

type MarkReadAck = {
  ok?: boolean
  message_ids?: number[]
  error?: string
}

type NavigatorWithUserAgentData = Navigator & {
  userAgentData?: {
    platform?: string
    brands?: UserAgentBrand[]
  }
}

type VisitorEnvironment = {
  system: string | null
  browser: string | null
}

const EMPTY_EMBED_INIT_PAYLOAD: EmbedInitPayload = {}
const URL_CONTEXT_TOKEN_PARAMS = ['contextToken', 'context_token'] as const

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function sanitizeMetadata(value: unknown): Record<string, unknown> | null {
  return sanitizePlainRecord(value, 8192)
}

function sanitizeContextObject(value: unknown): Record<string, unknown> | null {
  return sanitizePlainRecord(value, 16384)
}

function sanitizePlainRecord(value: unknown, maxLength: number): Record<string, unknown> | null {
  if (!isPlainRecord(value)) return null
  try {
    const json = JSON.stringify(value)
    if (!json || json.length > maxLength) return null
    const parsed = JSON.parse(json) as unknown
    return isPlainRecord(parsed) ? parsed : null
  } catch {
    return null
  }
}

function sanitizeContextToken(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const token = value.trim()
  return token || null
}

function readUrlContextToken(searchParams: SearchParamsReader): string | null {
  for (const name of URL_CONTEXT_TOKEN_PARAMS) {
    const token = sanitizeContextToken(searchParams.get(name))
    if (token) return token
  }
  return null
}

function hasUrlContextTokenParam(searchParams: SearchParamsReader): boolean {
  return URL_CONTEXT_TOKEN_PARAMS.some((name) => searchParams.has(name))
}

function stripUrlContextTokenParams() {
  if (typeof window === 'undefined') return
  try {
    const url = new URL(window.location.href)
    let changed = false
    for (const name of URL_CONTEXT_TOKEN_PARAMS) {
      if (url.searchParams.has(name)) {
        url.searchParams.delete(name)
        changed = true
      }
    }
    if (changed) {
      window.history.replaceState(window.history.state, document.title, `${url.pathname}${url.search}${url.hash}`)
    }
  } catch {
    // Keep the chat usable even if the browser refuses history replacement.
  }
}

function sanitizeEmbedVisitor(value: unknown): EmbedVisitorPayload | null {
  if (!isPlainRecord(value)) return null
  const visitor: EmbedVisitorPayload = {}
  if (typeof value.name === 'string') {
    const name = value.name.trim().slice(0, 64)
    if (name) visitor.name = name
  }
  const customer = sanitizeContextObject(value.customer)
  if (customer) visitor.customer = customer
  const metadata = sanitizeMetadata(value.metadata)
  if (metadata) visitor.metadata = metadata
  return Object.keys(visitor).length > 0 ? visitor : null
}

function sanitizeEmbedPayload(data: Record<string, unknown>): EmbedInitPayload {
  return {
    visitor: sanitizeEmbedVisitor(data.visitor),
    contextToken: sanitizeContextToken(data.contextToken),
    sessionSummary: sanitizeContextObject(data.sessionSummary),
  }
}

function browserLabel(name: string, version?: string): string {
  const major = version?.split('.')[0]
  return major ? `${name} ${major}` : name
}

function detectSystem(ua: string, platform: string): string | null {
  const android = ua.match(/Android\s+([\d.]+)/i)
  if (android?.[1]) return `Android ${android[1]}`

  const ios = ua.match(/(?:iPhone|iPad|iPod).*OS\s+([\d_]+)/i)
  if (ios?.[1]) return `iOS ${ios[1].replace(/_/g, '.')}`

  const mac = ua.match(/Mac OS X\s+([\d_]+)/i)
  if (mac?.[1]) return `macOS ${mac[1].replace(/_/g, '.')}`

  if (/Windows NT/i.test(ua)) return 'Windows'
  if (/Linux/i.test(ua)) return 'Linux'
  return platform || null
}

function detectBrowser(ua: string, brands?: UserAgentBrand[]): string | null {
  const edge = ua.match(/Edg(?:e|A|iOS)?\/([\d.]+)/i)
  if (edge?.[1]) return browserLabel('Edge', edge[1])

  const opera = ua.match(/(?:OPR|Opera)\/([\d.]+)/i)
  if (opera?.[1]) return browserLabel('Opera', opera[1])

  const firefox = ua.match(/(?:Firefox|FxiOS)\/([\d.]+)/i)
  if (firefox?.[1]) return browserLabel('Firefox', firefox[1])

  const chrome = ua.match(/(?:Chrome|CriOS)\/([\d.]+)/i)
  if (chrome?.[1]) return browserLabel('Chrome', chrome[1])

  const safari = ua.match(/Version\/([\d.]+).*Safari/i)
  if (safari?.[1]) return browserLabel('Safari', safari[1])

  const brand = brands?.find((item) => !/not|chromium/i.test(item.brand))
  return brand ? browserLabel(brand.brand, brand.version) : null
}

function detectVisitorEnvironment(): VisitorEnvironment {
  if (typeof navigator === 'undefined') {
    return { system: null, browser: null }
  }
  const nav = navigator as NavigatorWithUserAgentData
  const ua = nav.userAgent || ''
  const platform = nav.userAgentData?.platform || nav.platform || ''
  return {
    system: detectSystem(ua, platform),
    browser: detectBrowser(ua, nav.userAgentData?.brands),
  }
}

function visitorCredentialStorageKey(channelKey: string): string {
  return `opendesk_visitor_${channelKey}`
}

// Max automatic re-mint attempts before giving up and surfacing the auth error.
const MAX_SESSION_RECOVERIES = 3

// Max retries for a transient (non-auth) context-sync failure before giving up.
const MAX_CONTEXT_SYNC_RETRIES = 3

function getVisitorPayloadKey(payload?: EmbedInitPayload | null): string {
  return JSON.stringify({
    visitor: payload?.visitor || null,
    contextToken: payload?.contextToken || null,
  })
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

function isReadableAgentMessage(message: Message): boolean {
  return (
    message.sender_type === 'agent'
    && (
      message.content_type === 'text'
      || message.content_type === 'rich_text'
      || message.content_type === 'image'
      || message.content_type === 'file'
    )
  )
}

function mapPublicHistoryItem(item: VisitorConversationHistoryItem): VisitorConversationHistoryItem {
  return {
    ...item,
    messages: item.messages.map((message) => mapPublicMessage(message)),
  }
}

function mapUnreadOfflineReplyItem(item: VisitorUnreadOfflineReplyItem): VisitorUnreadOfflineReplyItem {
  return {
    ...item,
    messages: item.messages.map((message) => mapPublicMessage(message)),
  }
}

function isHumanHandoffEventPayload(value: unknown): value is HumanHandoffEventPayload {
  return Boolean(
    isPlainRecord(value)
      && value.event_kind === 'human_handoff'
      && value.schema_version === 1
      && isPlainRecord(value.handoff),
  )
}

function restorePendingHumanHandoff(messages: Message[]) {
  const confirmedToolCallIds = new Set<string>()
  for (const message of messages) {
    const metadata = message.metadata
    if (
      (
        metadata?.handoff_event_type === 'confirmed_by_visitor'
        || metadata?.handoff_event_type === 'auto_triggered'
      )
      && typeof metadata.tool_call_id === 'string'
    ) {
      confirmedToolCallIds.add(metadata.tool_call_id)
    }
  }

  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i]
    const metadata = message.metadata
    if (!metadata || metadata.event_type !== 'open_agent_handoff_event') continue

    const eventType = metadata.handoff_event_type
    if (eventType === 'confirmed_by_visitor' || eventType === 'auto_triggered') continue

    const toolCallId = typeof metadata.tool_call_id === 'string' ? metadata.tool_call_id : null
    if (toolCallId && confirmedToolCallIds.has(toolCallId)) continue

    const payload = metadata.handoff_payload
    if (!isHumanHandoffEventPayload(payload)) continue

    const brief =
      typeof payload.handoff.brief === 'string' && payload.handoff.brief.trim()
        ? payload.handoff.brief.trim()
        : message.content || '这个问题需要人工客服进一步处理。'
    return {
      payload,
      brief,
      messageId: message.id,
      toolCallId: toolCallId ?? undefined,
    }
  }
  return null
}

function getLocale(preferredLocale?: string | null): Locale {
  if (preferredLocale === 'zh' || preferredLocale === 'en') return preferredLocale
  if (typeof navigator === 'undefined') return 'en'
  const lang = navigator.language || 'en'
  return lang.startsWith('zh') ? 'zh' : 'en'
}

function postEmbedMessage(
  instanceId: string,
  message: { type: 'ready' | 'close' | 'error' | 'warning'; code?: string; message?: string; reason?: string },
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
  agent_default_avatar_url: null,
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
  outside_service_hours_strategy: 'offline_message',
  offline_title: '当前客服不在线',
  offline_message: '您好，当前客服不在线，您可以稍后再来咨询，我们会尽快为您服务。',
  leave_message_prompt: '请留下您的问题和联系方式，我们上线后会尽快联系您。',
  restricted_service_message: '抱歉，当前暂时无法为您提供在线咨询服务。如需帮助，请通过其他公开渠道联系服务方。',
  queue_message: '您已进入人工客服队列。当前排队人数：{{current_queue_count}} 位，请稍候。客服接入后会立即回复您。',
  queue_full_message: '当前排队人数较多，暂时无法进入排队。您可以稍后再试，或点击留言，我们上线后会尽快联系您。',
  queue_full_show_leave_message_button: true,
  queue_full_leave_message_button_label: '留言',
  open_agent_enabled: false,
  open_agent_agent_id: null,
  open_agent_agent_name: null,
  open_agent_bot_strategy: 'always',
  open_agent_bot_service_hours_id: null,
  open_agent_avatar_url: null,
  open_agent_input_placeholder: null,
  open_agent_handoff_enabled: true,
  open_agent_handoff_label: '转人工',
  open_agent_handoff_after_messages: 2,
  open_agent_handoff_behavior: 'confirm',
  open_agent_feedback_enabled: false,
  open_agent_custom_buttons_enabled: false,
  open_agent_custom_buttons: [],
  human_custom_buttons_enabled: false,
  human_custom_buttons: [],
  assist_panel_enabled: false,
  assist_panel_title: null,
  assist_panel_react_code: null,
  assist_panel_config: {},
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
  const urlContextToken = useMemo(
    () => embedInitRequired ? null : readUrlContextToken(searchParams),
    [embedInitRequired, searchParams],
  )
  const standaloneInitPayload = useMemo<EmbedInitPayload>(
    () => urlContextToken ? { contextToken: urlContextToken } : EMPTY_EMBED_INIT_PAYLOAD,
    [urlContextToken],
  )
  const visitorEnvironment = useMemo(() => detectVisitorEnvironment(), [])
  const isMobile = useIsMobile()
  const [visitorExternalId, setVisitorExternalId] = useState<string | null>(null)
  const [visitorSessionToken, setVisitorSessionToken] = useState<string | null>(null)
  const [offlineMessagePublicId, setOfflineMessagePublicId] = useState<string | null>(null)
  const [leaveMessageMode, setLeaveMessageMode] = useState(false)
  const [leaveMessagePrompt, setLeaveMessagePrompt] = useState('')
  const lastSyncedContextTokenRef = useRef<string | null>(null)
  // Bounds automatic re-mint attempts after a visitor session auth failure, so a
  // token the server keeps rejecting (e.g. a disabled channel) can't loop.
  const sessionRecoveryRef = useRef(0)
  // Tracks transient context-sync failures per token to cap backoff retries.
  const contextSyncFailureRef = useRef<{ token: string | null; failures: number }>({
    token: null,
    failures: 0,
  })
  const [contextSyncRetryNonce, setContextSyncRetryNonce] = useState(0)

  const {
    socket,
    connected,
    connecting,
    authFailed,
    conversationPublicId,
    messages,
    hasMore,
    satisfactionInvitation,
    pendingHumanHandoff,
    connect,
    clearAuthFailed,
    setConversationPublicId,
    setMessages,
    prependMessages,
    setHasMore,
    setSatisfactionInvitation,
    setPendingHumanHandoff,
  } = useVisitorChatStore()

  const {
    data: channel,
    error: channelError,
  } = useChannelPublic(channelKey, visitorExternalId, conversationPublicId)
  const { data: emojiConfig } = usePublicEmojiSettings()

  const [loadingMore, setLoadingMore] = useState(false)
  const [historyConversations, setHistoryConversations] = useState<VisitorConversationHistoryItem[]>([])
  const [historyHasMore, setHistoryHasMore] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyLoaded, setHistoryLoaded] = useState(false)
  const [historyError, setHistoryError] = useState(false)
  const [historyLimitReached, setHistoryLimitReached] = useState(false)
  const [unreadReplyConversations, setUnreadReplyConversations] = useState<VisitorUnreadOfflineReplyItem[]>([])
  const [unreadReplyHasMore, setUnreadReplyHasMore] = useState(false)
  const [unreadReplyError, setUnreadReplyError] = useState(false)
  const [unreadReplyChecked, setUnreadReplyChecked] = useState(false)
  const [currentUnreadReplyNotice, setCurrentUnreadReplyNotice] = useState<{
    conversationPublicId: string
    unread: boolean
  } | null>(null)
  const [ended, setEnded] = useState(false)
  const [conversationStatus, setConversationStatus] = useState<string | null>(null)
  const [satisfactionCanInitiate, setSatisfactionCanInitiate] = useState(false)
  const [satisfactionLoading, setSatisfactionLoading] = useState(false)
  const [readReceiptVisibilityNonce, setReadReceiptVisibilityNonce] = useState(0)
  const [socketOfflineTitle, setSocketOfflineTitle] = useState('')
  const [socketOfflineMessage, setSocketOfflineMessage] = useState('')
  const [queueFullMessage, setQueueFullMessage] = useState('')
  const [startConversationError, setStartConversationError] = useState<string | null>(null)
  const [queueFullShowLeaveMessageButton, setQueueFullShowLeaveMessageButton] = useState(true)
  const [queueFullLeaveMessageButtonLabel, setQueueFullLeaveMessageButtonLabel] = useState('')
  const [currentQueueCount, setCurrentQueueCount] = useState<number | null>(null)
  const [conversationInitializing, setConversationInitializing] = useState(true)
  const [embedReadyPosted, setEmbedReadyPosted] = useState(false)
  const [embedInitPayload, setEmbedInitPayload] = useState<EmbedInitPayload | null>(
    () => embedInitRequired ? null : standaloneInitPayload,
  )
  const [embedActivated, setEmbedActivated] = useState(
    () => !embedActivationRequired,
  )
  const startedRef = useRef(false)
  const customerReadInFlightRef = useRef<Set<string>>(new Set())
  const lastCustomerReadMessageRef = useRef<string | null>(null)
  const readReceiptConfirmedIdsRef = useRef<Map<string, Set<number>>>(new Map())
  const readReceiptInFlightKeysRef = useRef<Set<string>>(new Set())
  const readReceiptRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const conversationPublicIdRef = useRef<string | null>(null)
  // Offline UI is driven purely by the server's start_conversation response so
  // that a visitor with an unfinished conversation can always re-enter it,
  // regardless of whether any agent is currently online. The channel-level
  // availability hint is kept only as a fallback copy for the offline screen.
  const isLeaveMessage = leaveMessageMode && !conversationPublicId
  const queueFull = !!queueFullMessage && !isLeaveMessage && !startConversationError
  const isOffline = !!socketOfflineMessage && !conversationPublicId && !isLeaveMessage && !queueFull && !startConversationError

  useEffect(() => {
    conversationPublicIdRef.current = conversationPublicId
  }, [conversationPublicId])

  const trackEvent = useCallback((
    name: string,
    input: Parameters<typeof telemetry.track>[1] = {},
  ) => {
    telemetry.track(name, {
      ...input,
      channel_key: channelKey,
      conversation_external_id: input.conversation_external_id ?? conversationPublicIdRef.current,
      props: {
        embed: isEmbed,
        preload: isPreload,
        locale,
        ...(input.props ?? {}),
      },
    })
  }, [channelKey, isEmbed, isPreload, locale])

  const handleEmbedClose = useCallback(() => {
    trackEvent('chat_embed_close')
    postEmbedMessage(embedInstanceId, { type: 'close' })
  }, [embedInstanceId, trackEvent])

  useEffect(() => {
    if (!hasUrlContextTokenParam(searchParams)) return
    stripUrlContextTokenParams()
  }, [searchParams])

  useEffect(() => {
    setEmbedReadyPosted(false)
    setEmbedActivated(!embedActivationRequired)
    setEmbedInitPayload(embedInitRequired ? null : standaloneInitPayload)
  }, [channelKey, embedActivationRequired, embedInstanceId, embedInitRequired, standaloneInitPayload])

  useEffect(() => {
    if (!embedInitRequired) return

    const handleMessage = (event: MessageEvent) => {
      if (event.source !== window.parent) return
      const data = event.data as unknown
      if (
        !isPlainRecord(data) ||
        data.source !== 'opendesk-sdk' ||
        (data.type !== 'init' && data.type !== 'open' && data.type !== 'update_context') ||
        data.instanceId !== embedInstanceId
      ) {
        return
      }

      const nextPayload = sanitizeEmbedPayload(data)
      if (data.type === 'update_context') {
        setEmbedInitPayload((current) => ({
          ...(current ?? EMPTY_EMBED_INIT_PAYLOAD),
          ...nextPayload,
        }))
      } else {
        setEmbedInitPayload((current) => current ?? nextPayload)
      }
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
    trackEvent('chat_frame_ready')
    postEmbedMessage(embedInstanceId, { type: 'ready' })
    setEmbedReadyPosted(true)
  }, [channel, embedInstanceId, embedReadyPosted, isEmbed, trackEvent])

  useEffect(() => {
    if (!isEmbed || !embedInstanceId || !channelError) return
    trackEvent('channel_load_failed', {
      level: 'error',
      props: { error_type: 'channel_error' },
    })
    postEmbedMessage(embedInstanceId, {
      type: 'error',
      code: 'CONFIG_LOAD_FAILED',
      message: 'Failed to load OpenDesk channel config.',
    })
  }, [channelError, embedInstanceId, isEmbed, trackEvent])

  useEffect(() => {
    if (!channel) return
    trackEvent('channel_load_success', {
      props: {
        public_access_enabled: true,
        open_agent_enabled: channel.config.open_agent_enabled,
        assist_panel_enabled: channel.config.assist_panel_enabled,
      },
    })
  }, [channel, trackEvent])

  useEffect(() => {
    let cancelled = false
    if (!channelKey || !embedActivated || (embedInitRequired && embedInitPayload === null)) return
    const embedPayload = embedInitPayload ?? EMPTY_EMBED_INIT_PAYLOAD
    const embedVisitor = embedPayload.visitor
    const currentContextToken = embedPayload.contextToken || null
    const visitorPayloadKey = getVisitorPayloadKey(embedPayload)

    setVisitorExternalId(null)
    setVisitorSessionToken(null)
    setConversationPublicId(null)
    setOfflineMessagePublicId(null)
    setLeaveMessageMode(false)
    setLeaveMessagePrompt('')
    setMessages([])
    setHasMore(false)
    setHistoryConversations([])
    setHistoryHasMore(false)
    setHistoryLoading(false)
    setHistoryLoaded(false)
    setHistoryError(false)
    setHistoryLimitReached(false)
    setUnreadReplyConversations([])
    setUnreadReplyHasMore(false)
    setUnreadReplyError(false)
    setUnreadReplyChecked(false)
    setCurrentUnreadReplyNotice(null)
    setSatisfactionInvitation(null)
    setSatisfactionCanInitiate(false)
    setPendingHumanHandoff(null)
    setEnded(false)
    setConversationStatus(null)
    setSocketOfflineTitle('')
    setSocketOfflineMessage('')
    setQueueFullMessage('')
    setQueueFullShowLeaveMessageButton(true)
    setQueueFullLeaveMessageButtonLabel('')
    setStartConversationError(null)
    setCurrentQueueCount(null)
    setConversationInitializing(true)
    startedRef.current = false
    customerReadInFlightRef.current.clear()
    lastCustomerReadMessageRef.current = null
    lastSyncedContextTokenRef.current = null

    const createSession = async () => {
      const stored = readVisitorCredential(channelKey)
      const storedForRenewal = stored?.visitorPayloadKey === visitorPayloadKey ? stored : null
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
            visitorExternalId: storedForRenewal?.visitorExternalId,
            visitorSecret: storedForRenewal?.visitorSecret,
            visitorName: embedVisitor?.name,
            metadata: embedVisitor?.metadata,
            contextToken: currentContextToken,
          }),
          stored: storedForRenewal,
          reused: false,
        }
      } catch (error) {
        if (!storedForRenewal) throw error
        clearVisitorCredential(channelKey)
        return {
          session: await createVisitorSession({
            channelKey,
            visitorName: embedVisitor?.name,
            metadata: embedVisitor?.metadata,
            contextToken: currentContextToken,
          }),
          stored: null,
          reused: false,
        }
      }
    }

    createSession()
      .then(({ session, stored, reused }) => {
        if (cancelled) return
        trackEvent('visitor_session_ready', {
          props: {
            reused,
            has_context_token: Boolean(currentContextToken),
            has_visitor_payload: Boolean(embedVisitor),
            warning_count: session.context_warnings?.length ?? 0,
          },
        })
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
        if (session.context_warnings?.length && isEmbed && embedInstanceId) {
          postEmbedMessage(embedInstanceId, {
            type: 'warning',
            code: 'CONTEXT_PARTIAL_ACCEPTED',
            message: session.context_warnings.join(', '),
          })
        }
      })
      .catch(() => {
        if (!cancelled) {
          trackEvent('visitor_session_failed', {
            level: 'error',
            props: { has_context_token: Boolean(currentContextToken) },
          })
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
    setPendingHumanHandoff,
    isEmbed,
    embedInstanceId,
    trackEvent,
  ])

  const startConversation = useCallback(async () => {
    if (!socket || !connected || !visitorSessionToken) return
    const startedAt = Date.now()
    const currentContextToken = embedInitPayload?.contextToken || null
    const startPayload = {
      ...(currentContextToken ? { contextToken: currentContextToken } : {}),
      ...(visitorEnvironment.system ? { system: visitorEnvironment.system } : {}),
      ...(visitorEnvironment.browser ? { browser: visitorEnvironment.browser } : {}),
    }

    if (!conversationPublicId && !socketOfflineMessage) {
      setConversationInitializing(true)
    }
    trackEvent('conversation_start_requested', {
      props: {
        has_context_token: Boolean(currentContextToken),
        has_existing_conversation: Boolean(conversationPublicId),
      },
    })
    await new Promise<void>((resolve) => {
      let resolved = false
      const resolveOnce = () => {
        if (resolved) return
        resolved = true
        resolve()
      }
      const timer = window.setTimeout(() => {
        setConversationInitializing(false)
        trackEvent('conversation_start_timeout', {
          level: 'warn',
          metrics: { timeout_ms: 30000 },
        })
        resolveOnce()
      }, 30000)

      socket.emit(
        'start_conversation',
        startPayload,
        async (res: {
          ok?: boolean
          conversation?: { conversation_public_id: string; status?: string; queue_position?: number | null }
          queue_position?: number | null
          is_new?: boolean
          context_sync?: {
            ok?: boolean
            warnings?: string[]
            customer_synced?: boolean
            session_summary_synced?: boolean
          }
          error?: string
          reason?: string
          offline_title?: string
          offline_message?: string
          leave_message_prompt?: string
          restricted_service_title?: string
          restricted_service_message?: string
          queue_full_message?: string
          queue_full_show_leave_message_button?: boolean
          queue_full_leave_message_button_label?: string
        }) => {
          if (res.ok && res.conversation) {
            trackEvent('conversation_start_succeeded', {
              conversation_external_id: res.conversation.conversation_public_id,
              props: {
                is_new: res.is_new === true,
                status: res.conversation.status || 'unknown',
                context_synced: res.context_sync?.ok !== false,
              },
              metrics: { duration_ms: Date.now() - startedAt },
            })
            if (currentContextToken && res.context_sync?.ok !== false) {
              lastSyncedContextTokenRef.current = currentContextToken
            }
            if (res.context_sync?.ok === false && isEmbed && embedInstanceId) {
              postEmbedMessage(embedInstanceId, {
                type: 'error',
                code: 'CONTEXT_SYNC_FAILED',
                message: 'Failed to synchronize Web SDK context.',
              })
            } else if (res.context_sync?.warnings?.length && isEmbed && embedInstanceId) {
              postEmbedMessage(embedInstanceId, {
                type: 'warning',
                code: 'CONTEXT_PARTIAL_ACCEPTED',
                message: res.context_sync.warnings.join(', '),
              })
            }
            // Clear stale offline copy after a successful new or resumed conversation.
            setSocketOfflineTitle('')
            setSocketOfflineMessage('')
            setQueueFullMessage('')
            setQueueFullShowLeaveMessageButton(true)
            setQueueFullLeaveMessageButtonLabel('')
            setStartConversationError(null)
            setOfflineMessagePublicId(null)
            setLeaveMessageMode(false)
            setLeaveMessagePrompt('')
            setConversationPublicId(res.conversation.conversation_public_id)
            setConversationStatus(res.conversation.status || null)
            setCurrentQueueCount(
              typeof res.conversation.queue_position === 'number'
                ? res.conversation.queue_position
                : typeof res.queue_position === 'number'
                  ? res.queue_position
                  : null,
            )
            setEnded(res.conversation.status === 'closed')
            try {
              const fetchStartedAt = Date.now()
              const data = await fetchPublicMessages({
                conversationPublicId: res.conversation.conversation_public_id,
                visitorSessionToken,
                limit: 50,
              })
              trackEvent('conversation_messages_loaded', {
                conversation_external_id: res.conversation.conversation_public_id,
                props: { source: 'start_conversation' },
                metrics: {
                  duration_ms: Date.now() - fetchStartedAt,
                  message_count: data.items.length,
                },
              })
              const currentMessages = data.items.map(mapPublicMessage)
              setMessages(currentMessages)
              setHasMore(data.has_more)
              if (
                res.conversation.status === 'handoff_pending'
                && channel?.config.open_agent_handoff_behavior === 'confirm'
              ) {
                setPendingHumanHandoff(restorePendingHumanHandoff(currentMessages))
              } else {
                setPendingHumanHandoff(null)
              }
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
              trackEvent('conversation_messages_load_failed', {
                level: 'warn',
                conversation_external_id: res.conversation.conversation_public_id,
                props: { source: 'start_conversation' },
              })
              setMessages([])
              setHasMore(false)
              setPendingHumanHandoff(null)
              setSatisfactionCanInitiate(false)
            }
          } else if (res.error === 'RESTRICTED') {
            trackEvent('conversation_start_restricted', {
              props: { reason: res.reason || 'restricted' },
              metrics: { duration_ms: Date.now() - startedAt },
            })
            setConversationPublicId(null)
            setOfflineMessagePublicId(null)
            setLeaveMessageMode(false)
            setLeaveMessagePrompt('')
            setQueueFullMessage('')
            setQueueFullShowLeaveMessageButton(true)
            setQueueFullLeaveMessageButtonLabel('')
            setCurrentQueueCount(null)
            setMessages([])
            setHasMore(false)
            setPendingHumanHandoff(null)
            setSatisfactionInvitation(null)
            setSatisfactionCanInitiate(false)
            setEnded(false)
            setConversationStatus(null)
            setStartConversationError(null)
            setSocketOfflineTitle(
              res.restricted_service_title
              || (locale === 'zh' ? '当前暂时无法提供在线咨询' : 'Chat is temporarily unavailable'),
            )
            setSocketOfflineMessage(
              res.restricted_service_message
              || channel?.config.restricted_service_message
              || (locale === 'zh'
                ? '抱歉，当前暂时无法为您提供在线咨询服务。如需帮助，请通过其他公开渠道联系服务方。'
                : 'Sorry, online support is temporarily unavailable. If you need help, please contact the service provider through another published channel.'),
            )
          } else if (res.error === 'OFFLINE') {
            trackEvent('conversation_start_offline', {
              props: { reason: res.reason || 'offline' },
              metrics: { duration_ms: Date.now() - startedAt },
            })
            setConversationPublicId(null)
            setOfflineMessagePublicId(null)
            setLeaveMessageMode(false)
            setLeaveMessagePrompt('')
            setQueueFullMessage('')
            setQueueFullShowLeaveMessageButton(true)
            setQueueFullLeaveMessageButtonLabel('')
            setCurrentQueueCount(null)
            setMessages([])
            setHasMore(false)
            setSatisfactionInvitation(null)
            setSatisfactionCanInitiate(false)
            setEnded(false)
            setConversationStatus(null)
            setSocketOfflineTitle(res.offline_title || '')
            setSocketOfflineMessage(res.offline_message || '')
          } else if (res.error === 'LEAVE_MESSAGE') {
            trackEvent('conversation_start_leave_message', {
              props: { reason: res.reason || 'leave_message' },
              metrics: { duration_ms: Date.now() - startedAt },
            })
            setConversationPublicId(null)
            setSocketOfflineTitle('')
            setSocketOfflineMessage('')
            setQueueFullMessage('')
            setQueueFullShowLeaveMessageButton(true)
            setQueueFullLeaveMessageButtonLabel('')
            setCurrentQueueCount(null)
            setLeaveMessageMode(true)
            setSatisfactionInvitation(null)
            setSatisfactionCanInitiate(false)
            setEnded(false)
            setConversationStatus(null)
            setLeaveMessagePrompt(res.leave_message_prompt || channel?.config.leave_message_prompt || '')
            try {
              const data = await fetchCurrentOfflineMessage({ visitorSessionToken, limit: 50 })
              if (data?.conversation_public_id) {
                setOfflineMessagePublicId(null)
                setLeaveMessageMode(false)
                setConversationPublicId(data.conversation_public_id)
                setConversationStatus('active')
                const current = await fetchPublicMessages({
                  conversationPublicId: data.conversation_public_id,
                  visitorSessionToken,
                  limit: 50,
                })
                setMessages(current.items.map(mapPublicMessage))
                setHasMore(current.has_more)
              } else if (data) {
                setOfflineMessagePublicId(data.offline_message_public_id)
                setMessages(data.messages.map(mapPublicMessage))
                setHasMore(data.has_more)
              } else {
                setOfflineMessagePublicId(null)
                setMessages([])
                setHasMore(false)
              }
            } catch {
              trackEvent('offline_message_load_failed', {
                level: 'warn',
                props: { source: 'start_conversation' },
              })
              setOfflineMessagePublicId(null)
              setLeaveMessageMode(false)
              setMessages([])
              setHasMore(false)
              setSocketOfflineTitle(res.offline_title || '')
              setSocketOfflineMessage(res.offline_message || '')
            }
          } else if (res.error === 'NO_ASSIGNABLE_QUEUE') {
            trackEvent('conversation_start_no_assignable_queue', {
              props: { reason: res.reason || 'no_assignable_queue' },
              metrics: { duration_ms: Date.now() - startedAt },
            })
            setConversationPublicId(null)
            setOfflineMessagePublicId(null)
            setLeaveMessageMode(false)
            setMessages([])
            setHasMore(false)
            setSatisfactionInvitation(null)
            setSatisfactionCanInitiate(false)
            setEnded(false)
            setConversationStatus(null)
            setSocketOfflineTitle('')
            setSocketOfflineMessage('')
            setCurrentQueueCount(null)
            setQueueFullMessage('')
            setQueueFullShowLeaveMessageButton(true)
            setQueueFullLeaveMessageButtonLabel('')
            setStartConversationError(t('chat.start.noAssignableQueue', locale as Locale))
            if (isEmbed && embedInstanceId) {
              postEmbedMessage(embedInstanceId, {
                type: 'error',
                code: 'NO_ASSIGNABLE_QUEUE',
                message: t('chat.start.noAssignableQueue', locale as Locale),
              })
            }
          } else if (res.error === 'QUEUE_FULL') {
            trackEvent('conversation_start_queue_full', {
              props: { reason: res.reason || 'queue_full' },
              metrics: { duration_ms: Date.now() - startedAt },
            })
            setConversationPublicId(null)
            setOfflineMessagePublicId(null)
            setLeaveMessageMode(false)
            setLeaveMessagePrompt(res.leave_message_prompt || channel?.config.leave_message_prompt || '')
            setMessages([])
            setHasMore(false)
            setSatisfactionInvitation(null)
            setSatisfactionCanInitiate(false)
            setEnded(false)
            setConversationStatus(null)
            setSocketOfflineTitle('')
            setSocketOfflineMessage('')
            setCurrentQueueCount(null)
            setQueueFullMessage(res.queue_full_message || channel?.config.queue_full_message || '')
            setQueueFullShowLeaveMessageButton(res.queue_full_show_leave_message_button !== false)
            setQueueFullLeaveMessageButtonLabel(
              res.queue_full_leave_message_button_label
              || channel?.config.queue_full_leave_message_button_label
              || '',
            )
          }
          window.clearTimeout(timer)
          setConversationInitializing(false)
          resolveOnce()
        },
      )
    })
  }, [
    channel?.config.open_agent_handoff_behavior,
    channel?.config.leave_message_prompt,
    channel?.config.restricted_service_message,
    channel?.config.queue_full_leave_message_button_label,
    channel?.config.queue_full_message,
    embedInitPayload,
    embedInstanceId,
    isEmbed,
    socket,
    connected,
    conversationPublicId,
    setConversationPublicId,
    setMessages,
    setHasMore,
    setSatisfactionInvitation,
    setPendingHumanHandoff,
    socketOfflineMessage,
    visitorEnvironment.browser,
    visitorEnvironment.system,
    visitorSessionToken,
    trackEvent,
  ])

  useEffect(() => {
    let cancelled = false
    if (!visitorSessionToken || !embedActivated) return

    setUnreadReplyChecked(false)
    setUnreadReplyError(false)
    fetchUnreadOfflineReplies({ visitorSessionToken, limit: 3 })
      .then((data) => {
        if (cancelled) return
        const items = data.items.map(mapUnreadOfflineReplyItem)
        const current = [...items]
          .reverse()
          .find((item) => item.status !== 'closed')
        const currentId = current?.conversation_public_id ?? null
        setUnreadReplyConversations(
          items.filter((item) => item.conversation_public_id !== currentId),
        )
        setUnreadReplyHasMore(data.has_more)
        setCurrentUnreadReplyNotice(
          current
            ? {
                conversationPublicId: current.conversation_public_id,
                unread: current.offline_reply_unread,
              }
            : null,
        )
      })
      .catch(() => {
        if (!cancelled) {
          setUnreadReplyConversations([])
          setUnreadReplyHasMore(false)
          setUnreadReplyError(true)
          setCurrentUnreadReplyNotice(null)
        }
      })
      .finally(() => {
        if (!cancelled) setUnreadReplyChecked(true)
      })

    return () => {
      cancelled = true
    }
  }, [embedActivated, visitorSessionToken])

  const handleUnreadReplyVisible = useCallback((conversationPublicId: string) => {
    if (!visitorSessionToken || !conversationPublicId) return
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
    if (customerReadInFlightRef.current.has(conversationPublicId)) return

    customerReadInFlightRef.current.add(conversationPublicId)
    markConversationCustomerRead({
      conversationPublicId,
      visitorSessionToken,
    })
      .then(() => {
        setUnreadReplyConversations((prev) =>
          prev.map((item) =>
            item.conversation_public_id === conversationPublicId
              ? { ...item, offline_reply_unread: false }
              : item,
          ),
        )
        setCurrentUnreadReplyNotice((current) =>
          current?.conversationPublicId === conversationPublicId
            ? { ...current, unread: false }
            : current,
        )
      })
      .catch(() => {
        // Keep the local unread display so the visitor can see it again later.
      })
      .finally(() => {
        customerReadInFlightRef.current.delete(conversationPublicId)
      })
  }, [visitorSessionToken])

  useEffect(() => {
    if (!conversationPublicId || messages.length === 0) return
    const latest = messages[messages.length - 1]
    if (latest.sender_type !== 'agent') return
    const marker = `${conversationPublicId}:${latest.id}`
    if (lastCustomerReadMessageRef.current === marker) return
    lastCustomerReadMessageRef.current = marker
    handleUnreadReplyVisible(conversationPublicId)
  }, [conversationPublicId, handleUnreadReplyVisible, messages])

  useEffect(() => {
    if (typeof document === 'undefined') return

    const handleVisible = () => {
      if (document.visibilityState === 'visible') {
        setReadReceiptVisibilityNonce((value) => value + 1)
      }
    }

    document.addEventListener('visibilitychange', handleVisible)
    window.addEventListener('focus', handleVisible)
    return () => {
      document.removeEventListener('visibilitychange', handleVisible)
      window.removeEventListener('focus', handleVisible)
    }
  }, [])

  const scheduleReadReceiptRetry = useCallback(() => {
    if (readReceiptRetryTimerRef.current) return
    readReceiptRetryTimerRef.current = setTimeout(() => {
      readReceiptRetryTimerRef.current = null
      setReadReceiptVisibilityNonce((value) => value + 1)
    }, READ_RECEIPT_RETRY_DELAY_MS)
  }, [])

  useEffect(() => {
    return () => {
      if (readReceiptRetryTimerRef.current) {
        clearTimeout(readReceiptRetryTimerRef.current)
        readReceiptRetryTimerRef.current = null
      }
    }
  }, [])

  const agentReadableMessageIds = useMemo(
    () => messages
      .filter((message) => message.conversation_public_id === conversationPublicId && isReadableAgentMessage(message))
      .map((message) => message.id),
    [conversationPublicId, messages],
  )

  useEffect(() => {
    if (!socket || !connected || !conversationPublicId || agentReadableMessageIds.length === 0) return
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return

    const confirmedIds = readReceiptConfirmedIdsRef.current.get(conversationPublicId) ?? new Set<number>()
    const pendingIds = agentReadableMessageIds.filter((id) => !confirmedIds.has(id))
    if (pendingIds.length === 0) return

    const requestKey = `${conversationPublicId}:${pendingIds.join(',')}`
    if (readReceiptInFlightKeysRef.current.has(requestKey)) return
    readReceiptInFlightKeysRef.current.add(requestKey)

    trackEvent('read_receipt_mark_read_requested', {
      conversation_external_id: conversationPublicId,
      props: {
        source: 'visible_chat_page',
        visibility_state: typeof document !== 'undefined' ? document.visibilityState : 'unknown',
      },
      metrics: {
        pending_message_count: pendingIds.length,
        latest_message_id: pendingIds[pendingIds.length - 1] ?? 0,
      },
    })

    socket.timeout(READ_RECEIPT_ACK_TIMEOUT_MS).emit(
      'mark_read',
      { conversation_public_id: conversationPublicId },
      (error: Error | null, response?: MarkReadAck) => {
        readReceiptInFlightKeysRef.current.delete(requestKey)
        if (error || response?.ok === false) {
          trackEvent('read_receipt_mark_read_failed', {
            level: 'warn',
            conversation_external_id: conversationPublicId,
            props: {
              source: 'visible_chat_page',
              reason: error ? 'ack_timeout_or_error' : response?.error || 'server_rejected',
            },
            metrics: {
              pending_message_count: pendingIds.length,
              latest_message_id: pendingIds[pendingIds.length - 1] ?? 0,
            },
          })
          scheduleReadReceiptRetry()
          return
        }

        const nextConfirmed = new Set(readReceiptConfirmedIdsRef.current.get(conversationPublicId) ?? [])
        pendingIds.forEach((id) => nextConfirmed.add(id))
        readReceiptConfirmedIdsRef.current.set(conversationPublicId, nextConfirmed)
        trackEvent('read_receipt_mark_read_succeeded', {
          conversation_external_id: conversationPublicId,
          props: { source: 'visible_chat_page' },
          metrics: {
            pending_message_count: pendingIds.length,
            read_message_count: response?.message_ids?.length ?? 0,
            latest_message_id: pendingIds[pendingIds.length - 1] ?? 0,
          },
        })
      },
    )
  }, [
    agentReadableMessageIds,
    connected,
    conversationPublicId,
    readReceiptVisibilityNonce,
    scheduleReadReceiptRetry,
    socket,
    trackEvent,
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

  useEffect(() => {
    const contextToken = embedInitPayload?.contextToken || null
    if (!contextToken || !conversationPublicId || !visitorSessionToken) return
    if (lastSyncedContextTokenRef.current === contextToken) return

    let cancelled = false
    lastSyncedContextTokenRef.current = contextToken
    syncConversationContext({
      conversationPublicId,
      visitorSessionToken,
      contextToken,
    })
      .then((result) => {
        if (cancelled) return
        contextSyncFailureRef.current = { token: null, failures: 0 }
        trackEvent('conversation_context_sync_succeeded', {
          conversation_external_id: conversationPublicId,
          props: {
            customer_synced: result.customer_synced,
            session_summary_synced: result.session_summary_synced,
            warning_count: result.warnings?.length ?? 0,
          },
        })
        if (!result.warnings?.length || !isEmbed || !embedInstanceId) return
        postEmbedMessage(embedInstanceId, {
          type: 'warning',
          code: 'CONTEXT_PARTIAL_ACCEPTED',
          message: result.warnings.join(', '),
        })
      })
      .catch((error: unknown) => {
        if (cancelled) return
        const status = (error as { response?: { status?: number } })?.response?.status
        // 401/403 means the context token itself is invalid/expired. Retrying the
        // same token always fails, so don't — wait for the host to push a fresh
        // one via updateContext (a new token value re-triggers this effect).
        const isAuthError = status === 401 || status === 403
        trackEvent('conversation_context_sync_failed', {
          level: 'error',
          conversation_external_id: conversationPublicId,
          props: { auth_error: isAuthError, ...(typeof status === 'number' ? { status } : {}) },
        })
        if (isEmbed && embedInstanceId) {
          postEmbedMessage(embedInstanceId, {
            type: 'error',
            code: 'CONTEXT_SYNC_FAILED',
            reason: isAuthError ? 'context_token_expired' : 'sync_failed',
            message: isAuthError
              ? 'Web SDK context token expired; provide a fresh token via updateContext.'
              : 'Failed to synchronize Web SDK context.',
          })
        }
        if (isAuthError) return

        // Transient failure: keep the token pinned but schedule a bounded,
        // backing-off retry of the same token.
        const prev = contextSyncFailureRef.current
        const failures = prev.token === contextToken ? prev.failures + 1 : 1
        contextSyncFailureRef.current = { token: contextToken, failures }
        if (failures <= MAX_CONTEXT_SYNC_RETRIES) {
          const delay = Math.min(1000 * 2 ** (failures - 1), 8000)
          lastSyncedContextTokenRef.current = null
          window.setTimeout(() => {
            if (!cancelled) setContextSyncRetryNonce((n) => n + 1)
          }, delay)
        }
      })

    return () => {
      cancelled = true
    }
  }, [conversationPublicId, embedInitPayload?.contextToken, embedInstanceId, isEmbed, visitorSessionToken, trackEvent, contextSyncRetryNonce])

  const handleSatisfactionSubmitted = useCallback(() => {
    setSatisfactionCanInitiate(false)
  }, [])

  const handleRestartConversation = useCallback(async () => {
    if (!socket || !connected || !visitorSessionToken) {
      await startConversation()
      return
    }
    setConversationInitializing(true)
    // Reset the loaded history so the "view previous conversations" entry
    // reappears: the conversation that just closed is no longer the current
    // one, so a fresh history fetch will surface it as a past conversation.
    setHistoryConversations([])
    setHistoryHasMore(false)
    setHistoryLoaded(false)
    setHistoryError(false)
    setHistoryLimitReached(false)
    setConversationPublicId(null)
    setMessages([])
    setHasMore(false)
    setSatisfactionInvitation(null)
    setSatisfactionCanInitiate(false)
    setPendingHumanHandoff(null)
    setEnded(false)
    setConversationStatus(null)
    setSocketOfflineTitle('')
    setSocketOfflineMessage('')
    setQueueFullMessage('')
    setQueueFullShowLeaveMessageButton(true)
    setQueueFullLeaveMessageButtonLabel('')
    setCurrentQueueCount(null)
    setStartConversationError(null)
    await startConversation()
  }, [
    connected,
    setConversationPublicId,
    setHasMore,
    setMessages,
    setPendingHumanHandoff,
    setSatisfactionInvitation,
    socket,
    startConversation,
    visitorSessionToken,
  ])

  const handleQueueFullLeaveMessage = useCallback(() => {
    setQueueFullMessage('')
    setQueueFullShowLeaveMessageButton(true)
    setQueueFullLeaveMessageButtonLabel('')
    setCurrentQueueCount(null)
    setSocketOfflineTitle('')
    setSocketOfflineMessage('')
    setConversationPublicId(null)
    setOfflineMessagePublicId(null)
    setLeaveMessageMode(true)
    setLeaveMessagePrompt((current) => current || channel?.config.leave_message_prompt || '')
    setMessages([])
    setHasMore(false)
    setEnded(false)
    setConversationStatus(null)
  }, [channel?.config.leave_message_prompt, setConversationPublicId, setHasMore, setMessages])

  const handleHandoffLeaveMessage = useCallback((prompt?: string) => {
    setQueueFullMessage('')
    setQueueFullShowLeaveMessageButton(true)
    setQueueFullLeaveMessageButtonLabel('')
    setCurrentQueueCount(null)
    setSocketOfflineTitle('')
    setSocketOfflineMessage('')
    setConversationPublicId(null)
    setOfflineMessagePublicId(null)
    setLeaveMessageMode(true)
    setLeaveMessagePrompt(prompt || channel?.config.leave_message_prompt || '')
    setMessages([])
    setHasMore(false)
    setEnded(false)
    setConversationStatus(null)
    setPendingHumanHandoff(null)
  }, [
    channel?.config.leave_message_prompt,
    setConversationPublicId,
    setHasMore,
    setMessages,
    setPendingHumanHandoff,
  ])

  const handleHandoffQueueFull = useCallback((payload: {
    queue_full_message?: string
    queue_full_show_leave_message_button?: boolean
    queue_full_leave_message_button_label?: string
    leave_message_prompt?: string
  }) => {
    setSocketOfflineTitle('')
    setSocketOfflineMessage('')
    setCurrentQueueCount(null)
    setLeaveMessageMode(false)
    setLeaveMessagePrompt(payload.leave_message_prompt || channel?.config.leave_message_prompt || '')
    setQueueFullMessage(payload.queue_full_message || channel?.config.queue_full_message || '')
    setQueueFullShowLeaveMessageButton(payload.queue_full_show_leave_message_button !== false)
    setQueueFullLeaveMessageButtonLabel(
      payload.queue_full_leave_message_button_label
      || channel?.config.queue_full_leave_message_button_label
      || '',
    )
    setPendingHumanHandoff(null)
  }, [
    channel?.config.leave_message_prompt,
    channel?.config.queue_full_leave_message_button_label,
    channel?.config.queue_full_message,
    setPendingHumanHandoff,
  ])

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
    if (!embedActivated || !channel || !visitorExternalId || !visitorSessionToken || connected || connecting || authFailed) return
    trackEvent('socket_connect_requested')
    connect(visitorSessionToken, visitorExternalId)
  }, [channel, connected, connecting, authFailed, connect, embedActivated, visitorExternalId, visitorSessionToken, trackEvent])

  // ── Auth-failure self-heal ──
  // An expired visitor session token makes the socket reject every reconnect.
  // Rather than leaving the chat dead until a manual page reload, mint a fresh
  // token for the same stored visitor identity and let the connect effect retry.
  // Bounded by MAX_SESSION_RECOVERIES so a token the server keeps rejecting
  // (e.g. a disabled channel, where minting itself fails) can't loop.
  useEffect(() => {
    if (!authFailed || !embedActivated || !channelKey) return
    if (sessionRecoveryRef.current >= MAX_SESSION_RECOVERIES) return
    sessionRecoveryRef.current += 1

    let cancelled = false
    const embedPayload = embedInitPayload ?? EMPTY_EMBED_INIT_PAYLOAD
    const stored = readVisitorCredential(channelKey)

    createVisitorSession({
      channelKey,
      visitorExternalId: stored?.visitorExternalId,
      visitorSecret: stored?.visitorSecret,
      visitorName: embedPayload.visitor?.name,
      metadata: embedPayload.visitor?.metadata,
      contextToken: embedPayload.contextToken || null,
    })
      .then((session) => {
        if (cancelled) return
        const visitorSecret = session.visitor_secret || stored?.visitorSecret
        if (visitorSecret) {
          writeVisitorCredential(channelKey, {
            visitorExternalId: session.visitor_external_id,
            visitorSecret,
            visitorSessionToken: session.visitor_session_token,
            visitorSessionExpiresAt: Date.now() + session.expires_in * 1000,
            visitorPayloadKey: getVisitorPayloadKey(embedPayload),
          })
        }
        setVisitorExternalId(session.visitor_external_id)
        setVisitorSessionToken(session.visitor_session_token)
        // Re-enable the connect effect now that a fresh token is in place.
        clearAuthFailed()
      })
      .catch(() => {
        // Minting failed (e.g. the channel was disabled). Leave authFailed set so
        // the page surfaces the error instead of silently retrying forever.
      })

    return () => {
      cancelled = true
    }
  }, [authFailed, embedActivated, channelKey, embedInitPayload, clearAuthFailed])

  useEffect(() => {
    if (!connected) return
    // A successful connect means the current token works; reset the recovery
    // budget so a later expiry gets a fresh set of attempts.
    sessionRecoveryRef.current = 0
    trackEvent('socket_connected')
  }, [connected, trackEvent])

  // ── Start conversation ──
  useEffect(() => {
    if (!embedActivated || !socket || !connected || !unreadReplyChecked || startedRef.current) return
    // After the conversation has ended, a reconnect (e.g. the server restarting
    // during a deploy) must not silently spin up a brand-new conversation: the
    // closed one can't be resumed server-side, so auto-starting would create an
    // unwanted session. A fresh conversation only happens when the visitor taps
    // the restart button (handleRestartConversation).
    if (ended) return
    startedRef.current = true
    void startConversation()
  }, [socket, connected, embedActivated, startConversation, unreadReplyChecked, ended])

  useEffect(() => {
    if (!socket) return

    const handleDisconnect = () => {
      startedRef.current = false
      trackEvent('socket_disconnected', { level: 'warn' })
    }

    socket.on('disconnect', handleDisconnect)
    return () => {
      socket.off('disconnect', handleDisconnect)
    }
  }, [socket, trackEvent])

  useEffect(() => {
    if (!socket) return
    const handler = (data: { conversation_public_id?: string }) => {
      if (!data.conversation_public_id || data.conversation_public_id === conversationPublicId) {
        trackEvent('conversation_assigned', {
          conversation_external_id: data.conversation_public_id ?? conversationPublicId,
        })
        setConversationStatus('active')
        setCurrentQueueCount(null)
      }
    }
    socket.on('conversation_assigned', handler)
    return () => {
      socket.off('conversation_assigned', handler)
    }
  }, [conversationPublicId, socket, trackEvent])

  useEffect(() => {
    if (conversationStatus === 'queued' || conversationStatus === 'active') return
    const hasQueueEnteredMessage = messages.some(isVisitorQueueEnteredMessage)
    if (hasQueueEnteredMessage) {
      setConversationStatus('queued')
    }
  }, [conversationStatus, messages])

  useEffect(() => {
    if (!socket || !visitorSessionToken) return
    const handler = (data: {
      offline_message_public_id?: string
      conversation_public_id?: string
      status?: string
    }) => {
      if (!data.conversation_public_id) return
      if (
        offlineMessagePublicId
        && data.offline_message_public_id
        && data.offline_message_public_id !== offlineMessagePublicId
      ) {
        return
      }
      setOfflineMessagePublicId(null)
      setLeaveMessageMode(false)
      setLeaveMessagePrompt('')
      setSocketOfflineTitle('')
      setSocketOfflineMessage('')
      setQueueFullMessage('')
      setQueueFullShowLeaveMessageButton(true)
      setQueueFullLeaveMessageButtonLabel('')
      setCurrentQueueCount(null)
      setConversationPublicId(data.conversation_public_id)
      setConversationStatus(data.status || 'active')
      setEnded(false)
      trackEvent('offline_message_conversation_created', {
        conversation_external_id: data.conversation_public_id,
        props: { status: data.status || 'active' },
      })
      fetchPublicMessages({
        conversationPublicId: data.conversation_public_id,
        visitorSessionToken,
        limit: 50,
      })
        .then((res) => {
          setMessages(res.items.map(mapPublicMessage))
          setHasMore(res.has_more)
        })
        .catch(() => {
          setMessages([])
          setHasMore(false)
        })
    }
    socket.on('offline_message_conversation_created', handler)
    return () => {
      socket.off('offline_message_conversation_created', handler)
    }
  }, [
    offlineMessagePublicId,
    setConversationPublicId,
    setHasMore,
    setMessages,
    socket,
    visitorSessionToken,
  ])

  // ── Conversation ended listener ──
  useEffect(() => {
    if (!socket) return
    const handler = () => {
      trackEvent('conversation_ended')
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
    if (!visitorSessionToken || loadingMore || !hasMore) return
    const oldest = messages[0]
    if (!oldest) return
    setLoadingMore(true)
    try {
      if (offlineMessagePublicId && !conversationPublicId) {
        const data = await fetchOfflineMessages({
          offlineMessagePublicId,
          visitorSessionToken,
          beforeId: oldest.id,
          limit: 50,
        })
        prependMessages(data.messages.map(mapPublicMessage))
        setHasMore(data.has_more)
      } else if (conversationPublicId) {
        const data = await fetchPublicMessages({
          conversationPublicId,
          visitorSessionToken,
          beforeId: oldest.id,
          limit: 20,
        })
        prependMessages(data.items.map(mapPublicMessage))
        setHasMore(data.has_more)
      }
    } catch {
      // ignore
    } finally {
      setLoadingMore(false)
    }
  }, [
    conversationPublicId,
    offlineMessagePublicId,
    visitorSessionToken,
    loadingMore,
    hasMore,
    messages,
    prependMessages,
    setHasMore,
  ])

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
  const runtimeConfig = useMemo(
    () => (
      isLeaveMessage && leaveMessagePrompt
        ? { ...config, leave_message_prompt: leaveMessagePrompt }
        : config
    ),
    [config, isLeaveMessage, leaveMessagePrompt],
  )
  const botMode =
    !isLeaveMessage &&
    config.open_agent_enabled
    && (conversationStatus === 'bot' || conversationStatus === 'handoff_pending')
  const pageBg = config.page_bg_color || 'var(--color-muted)'
  const offlineTitle = socketOfflineTitle || channel?.availability?.offline_title || config.offline_title
  const offlineMessage = socketOfflineMessage || channel?.availability?.offline_message || config.offline_message
  const showConnectionStatus = Boolean(socket) && !connected && !connecting && !isOffline
  const showAssistPanel = Boolean(
    !isEmbed
    && !isMobile
    && config.assist_panel_enabled
    && config.assist_panel_react_code?.trim(),
  )
  const historyAvailable = channel?.has_conversation_history === true || historyConversations.length > 0

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
      {showAssistPanel ? (
        <VisitorChatRuntimeProvider
          socket={socket}
          channel={channel}
          config={runtimeConfig}
          locale={locale}
          isMobile={isMobile}
          ended={ended}
          conversationStatus={conversationStatus}
          conversationPublicId={conversationPublicId}
          offlineMode={isLeaveMessage}
          offlineMessagePublicId={offlineMessagePublicId}
          queueFull={queueFull}
          queueFullMessage={queueFullMessage}
          queueFullShowLeaveMessageButton={queueFullShowLeaveMessageButton}
          queueFullLeaveMessageButtonLabel={queueFullLeaveMessageButtonLabel}
          startConversationError={startConversationError}
          currentQueueCount={currentQueueCount}
          visitorSessionToken={visitorSessionToken}
          visitorEnvironment={visitorEnvironment}
          hasMore={hasMore}
          loadingMore={loadingMore}
          historyAvailable={historyAvailable}
          historyConversations={historyConversations}
          historyHasMore={historyHasMore}
          historyLoading={historyLoading}
          historyLoaded={historyLoaded}
          historyError={historyError}
          historyLimitReached={historyLimitReached}
          unreadReplyConversations={unreadReplyConversations}
          unreadReplyHasMore={unreadReplyHasMore}
          unreadReplyError={unreadReplyError}
          currentUnreadReplyNotice={currentUnreadReplyNotice}
          initializing={conversationInitializing}
          botMode={botMode}
          visitorMessageCount={messages.filter((msg) => msg.sender_type === 'visitor').length}
          pendingHumanHandoff={pendingHumanHandoff}
          satisfactionCanInitiate={satisfactionCanInitiate}
          satisfactionLoading={satisfactionLoading}
          emojiConfig={emojiConfig ?? null}
          onLoadMore={handleLoadMore}
          onLoadHistory={handleLoadHistory}
          onUnreadReplyVisible={handleUnreadReplyVisible}
          onTyping={handleTyping}
          onRestartConversation={handleRestartConversation}
          onQueueFullLeaveMessage={handleQueueFullLeaveMessage}
          onHandoffLeaveMessage={handleHandoffLeaveMessage}
          onHandoffQueueFull={handleHandoffQueueFull}
          onConversationStatusChange={setConversationStatus}
          onCurrentQueueCountChange={setCurrentQueueCount}
          onOfflineMessageCreated={setOfflineMessagePublicId}
          onSatisfactionInitiate={handleSatisfactionInitiate}
          onSatisfactionSubmitted={handleSatisfactionSubmitted}
        >
          <div className="mx-auto flex min-h-0 w-full max-w-[1120px] flex-1 p-4">
            <div className="flex min-h-0 w-full flex-col overflow-hidden rounded-xl bg-background shadow-xl">
              <ChatHeader
                channel={channel}
                isMobile={isMobile}
                isEmbed={isEmbed}
                onEmbedClose={handleEmbedClose}
              />
              <div className="flex min-h-0 flex-1">
                <div className="flex min-h-0 min-w-[480px] flex-1 flex-col overflow-hidden">
                  <VisitorThread
                    offlineTitle={isOffline ? offlineTitle : undefined}
                    offlineMessage={isOffline ? offlineMessage : undefined}
                    isEmbed={isEmbed}
                    showHeader={false}
                    onEmbedClose={handleEmbedClose}
                  />
                </div>
                <VisitorAssistPanel />
              </div>
            </div>
          </div>
        </VisitorChatRuntimeProvider>
      ) : (
        <div className={chatContainerClassName}>
          <VisitorChatRuntimeProvider
            socket={socket}
            channel={channel}
            config={runtimeConfig}
            locale={locale}
            isMobile={isMobile}
            ended={ended}
            conversationStatus={conversationStatus}
            conversationPublicId={conversationPublicId}
            offlineMode={isLeaveMessage}
            offlineMessagePublicId={offlineMessagePublicId}
            queueFull={queueFull}
            queueFullMessage={queueFullMessage}
            queueFullShowLeaveMessageButton={queueFullShowLeaveMessageButton}
            queueFullLeaveMessageButtonLabel={queueFullLeaveMessageButtonLabel}
            startConversationError={startConversationError}
            currentQueueCount={currentQueueCount}
            visitorSessionToken={visitorSessionToken}
            visitorEnvironment={visitorEnvironment}
            hasMore={hasMore}
            loadingMore={loadingMore}
            historyAvailable={historyAvailable}
            historyConversations={historyConversations}
            historyHasMore={historyHasMore}
            historyLoading={historyLoading}
            historyLoaded={historyLoaded}
            historyError={historyError}
            historyLimitReached={historyLimitReached}
            unreadReplyConversations={unreadReplyConversations}
            unreadReplyHasMore={unreadReplyHasMore}
            unreadReplyError={unreadReplyError}
            currentUnreadReplyNotice={currentUnreadReplyNotice}
            initializing={conversationInitializing}
            botMode={botMode}
            visitorMessageCount={messages.filter((msg) => msg.sender_type === 'visitor').length}
            pendingHumanHandoff={pendingHumanHandoff}
            satisfactionCanInitiate={satisfactionCanInitiate}
            satisfactionLoading={satisfactionLoading}
            emojiConfig={emojiConfig ?? null}
            onLoadMore={handleLoadMore}
            onLoadHistory={handleLoadHistory}
            onUnreadReplyVisible={handleUnreadReplyVisible}
            onTyping={handleTyping}
            onRestartConversation={handleRestartConversation}
            onQueueFullLeaveMessage={handleQueueFullLeaveMessage}
            onHandoffLeaveMessage={handleHandoffLeaveMessage}
            onHandoffQueueFull={handleHandoffQueueFull}
            onConversationStatusChange={setConversationStatus}
            onCurrentQueueCountChange={setCurrentQueueCount}
            onOfflineMessageCreated={setOfflineMessagePublicId}
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
      )}

      {/* AGPL §13: visitors interacting with this network service must be
          offered the Corresponding Source. Compact variant keeps the chat UX
          uncluttered on both mobile and desktop. */}
      <LegalFooter locale={footerLocale} compact />
    </div>
  )
}
