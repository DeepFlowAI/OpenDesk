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
  leaveQueuedConversationMessage,
  markConversationCustomerRead,
  syncConversationContext,
  useChannelPublic,
  type ChannelPublicConfig,
  type OfflineMessageSource,
  type OfflineMessageQueueType,
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
import { resolveVisitorLocale } from '@/lib/languages'
import { t } from '@/utils/i18n'
import type {
  Message,
  VisitorConversationHistoryItem,
  VisitorUnreadOfflineReplyItem,
} from '@/models/conversation'
import type { ChannelConfig } from '@/models/channel'
import { cn } from '@/lib/utils'
import { isVisitorQueueEnteredMessage } from '@/lib/visitor-queue-notice'
import {
  bindVisitorMessageAlertUnlock,
  playVisitorMessageAlert,
  readVisitorMessageAlertEnabled,
  setVisitorMessageAlertEnabled,
  stopVisitorMessageAlert,
  unlockVisitorMessageAlert,
} from '@/lib/visitor-message-alert'
import { emitTestEvent, initTestEventChannel } from '@/lib/e2e-test-events'
import { buildMessageDeliveryBatches } from '@/lib/message-delivery'
import {
  getVisitorPayloadKey,
  mergeEmbedInitPayload,
  resolveVisitorIdentitySource,
  selectStoredVisitorCredential,
  shouldAutoStartConversation,
  type VisitorCredential,
  type VisitorInitSource,
} from '@/lib/visitor-session-credential'
import { FormMessage } from '@/app/components/features/visitor-chat/form-message'
import type { FormMessageSource } from '@/models/form-message'

const HISTORY_PAGE_SIZE = 10
const HISTORY_CLIENT_LIMIT = 200
const READ_RECEIPT_ACK_TIMEOUT_MS = 5000
const READ_RECEIPT_RETRY_DELAY_MS = 1200
const CONVERSATION_JOIN_ACK_TIMEOUT_MS = 2500
const CONVERSATION_JOIN_RETRY_DELAYS_MS = [0, 600, 1800] as const

type ConversationSubscriptionStatus = 'idle' | 'joining' | 'joined' | 'degraded'

// ─── Utilities ───────────────────────────────────────────────────

type OfflineMessageQueueTarget = {
  queueType: OfflineMessageQueueType
  queueId: number
}

function queueTargetFromPayload(payload: {
  queue_type?: string
  queue_id?: number | null
}): OfflineMessageQueueTarget | null {
  return payload.queue_type === 'employee_group' && typeof payload.queue_id === 'number'
    ? { queueType: payload.queue_type, queueId: payload.queue_id }
    : null
}

type EmbedVisitorPayload = {
  name?: string
  customer?: Record<string, unknown>
  metadata?: Record<string, unknown>
}

type EmbedInitPayload = {
  visitor?: EmbedVisitorPayload | null
  /** `undefined` = absent; `null` = explicit logout; string = active token */
  contextToken?: string | null
  sessionSummary?: Record<string, unknown> | null
  initSource?: VisitorInitSource
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

type JoinConversationAck = {
  ok?: boolean
  error?: string
  message?: string
  conversation_id?: number
  conversation_public_id?: string
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
// How long to wait for the SDK `init` message before falling back to an
// identity-less session, and how much longer before that fallback is also
// allowed to open a conversation (a stale host SDK may never send `init`).
const EMBED_INIT_FALLBACK_MS = 3000
const EMBED_INIT_GRACE_MS = 5000
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

/**
 * Preserve absent vs explicit-null for contextToken.
 * - missing field → undefined (safe to reuse stored identity)
 * - null / empty string → null when allowExplicitNull, else undefined
 * - non-empty string → token
 */
function sanitizeContextTokenField(
  data: Record<string, unknown>,
  allowExplicitNull: boolean,
): string | null | undefined {
  if (!Object.prototype.hasOwnProperty.call(data, 'contextToken')) return undefined
  const raw = data.contextToken
  if (raw === null || raw === '') {
    return allowExplicitNull ? null : undefined
  }
  if (typeof raw !== 'string') {
    return allowExplicitNull ? null : undefined
  }
  return sanitizeContextToken(raw) ?? (allowExplicitNull ? null : undefined)
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

function sanitizeEmbedPayload(
  data: Record<string, unknown>,
  options?: { allowExplicitNullToken?: boolean },
): EmbedInitPayload {
  const allowExplicitNullToken = Boolean(options?.allowExplicitNullToken)
  const payload: EmbedInitPayload = { initSource: 'sdk' }

  if (Object.prototype.hasOwnProperty.call(data, 'visitor')) {
    payload.visitor = data.visitor == null ? null : sanitizeEmbedVisitor(data.visitor)
  }
  if (Object.prototype.hasOwnProperty.call(data, 'contextToken')) {
    const token = sanitizeContextTokenField(data, allowExplicitNullToken)
    // Omit the key when the token is merely absent so update_context merges
    // do not wipe a previously established identity.
    if (token !== undefined) {
      payload.contextToken = token
    }
  }
  if (Object.prototype.hasOwnProperty.call(data, 'sessionSummary')) {
    payload.sessionSummary = sanitizeContextObject(data.sessionSummary)
  }
  return payload
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

function restorePendingHumanHandoff(messages: Message[], locale: Locale) {
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
        : message.content || t('chat.handoff.needsAgent', locale)
    return {
      payload,
      brief,
      messageId: message.id,
      toolCallId: toolCallId ?? undefined,
    }
  }
  return null
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
  language_strategy: 'browser',
  default_language: 'en',
  service_hours_enabled: false,
  service_hours_id: null,
  outside_service_hours_strategy: 'offline_message',
  offline_title: '当前客服不在线',
  offline_message: '您好，当前客服不在线，您可以稍后再来咨询，我们会尽快为您服务。',
  leave_message_prompt: '请留下您的问题和联系方式，我们上线后会尽快联系您。',
  leave_message_mode: 'conversation',
  form_message_config: {
    title: '请留下您的信息',
    description: '请填写以下信息，我们会尽快与您联系。',
    submit_label: '提交',
    success_title: '提交成功',
    success_description: '我们已收到您的信息，会尽快与您联系。',
    show_ticket_number: true,
    fields: [],
  },
  form_message_config_version: null,
  restricted_service_message: '抱歉，当前暂时无法为您提供在线咨询服务。如需帮助，请通过其他公开渠道联系服务方。',
  queue_message: '您已进入人工客服队列。当前排队人数：{{current_queue_count}} 位，请稍候。客服接入后会立即回复您。',
  queue_full_message: '当前排队人数较多，暂时无法进入排队。您可以稍后再试，或点击留言，我们上线后会尽快联系您。',
  queue_show_leave_message_button: false,
  queue_leave_message_button_label: '留言',
  queue_full_show_leave_message_button: true,
  queue_full_leave_message_button_label: '留言',
  open_agent_enabled: false,
  open_agent_agent_id: null,
  open_agent_agent_name: null,
  open_agent_bot_strategy: 'always',
  open_agent_bot_service_hours_id: null,
  open_agent_avatar_url: null,
  open_agent_input_placeholder: null,
  open_agent_attachment_upload_enabled: false,
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
  messageSoundEnabled,
  onMessageSoundEnabledChange,
}: {
  channel: ChannelPublicConfig
  config: ChannelConfig
  locale: Locale
  isMobile: boolean
  isEmbed: boolean
  onEmbedClose: () => void
  messageSoundEnabled: boolean
  onMessageSoundEnabledChange: (enabled: boolean) => void
}) {
  const placeholder =
    config.input_placeholder ||
    t('chat.input.placeholder', locale)

  return (
    <>
      <ChatHeader
        channel={channel}
        isMobile={isMobile}
        isEmbed={isEmbed}
        onEmbedClose={onEmbedClose}
        locale={locale}
        messageSoundEnabled={messageSoundEnabled}
        onMessageSoundEnabledChange={onMessageSoundEnabledChange}
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
  const urlContextToken = useMemo(
    () => embedInitRequired ? null : readUrlContextToken(searchParams),
    [embedInitRequired, searchParams],
  )
  const standaloneInitPayload = useMemo<EmbedInitPayload>(
    () =>
      urlContextToken
        ? { contextToken: urlContextToken, initSource: 'standalone' }
        : { initSource: 'standalone' },
    [urlContextToken],
  )
  const visitorEnvironment = useMemo(() => detectVisitorEnvironment(), [])
  const isMobile = useIsMobile()
  const [visitorExternalId, setVisitorExternalId] = useState<string | null>(null)
  const [visitorSessionToken, setVisitorSessionToken] = useState<string | null>(null)
  const [offlineMessagePublicId, setOfflineMessagePublicId] = useState<string | null>(null)
  const [offlineMessageSource, setOfflineMessageSource] = useState<OfflineMessageSource | null>(null)
  const [offlineMessageQueueTarget, setOfflineMessageQueueTarget] = useState<OfflineMessageQueueTarget | null>(null)
  const [leaveMessageMode, setLeaveMessageMode] = useState(false)
  const [leaveMessagePrompt, setLeaveMessagePrompt] = useState('')
  const [queueLeaveMessageLoading, setQueueLeaveMessageLoading] = useState(false)
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
  const [conversationSubscriptionStatus, setConversationSubscriptionStatus] =
    useState<ConversationSubscriptionStatus>('idle')
  const [conversationSubscriptionRetryNonce, setConversationSubscriptionRetryNonce] = useState(0)

  const {
    socket,
    connected,
    connecting,
    authFailed,
    connectionEpoch,
    conversationPublicId,
    messages,
    messageAlertNonce,
    hasMore,
    satisfactionInvitation,
    pendingHumanHandoff,
    connect,
    clearAuthFailed,
    setConversationPublicId,
    setMessages,
    reconcileConversationMessages,
    prependMessages,
    setHasMore,
    setSatisfactionInvitation,
    setPendingHumanHandoff,
  } = useVisitorChatStore()

  const {
    data: channel,
    error: channelError,
  } = useChannelPublic(channelKey, visitorExternalId, conversationPublicId)
  const locale = useMemo(
    () => resolveVisitorLocale(preferredLocale, channel?.config),
    [channel?.config.default_language, channel?.config.language_strategy, preferredLocale],
  )
  const channelLoaded = Boolean(channel)
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
  const deliveryReceiptAcknowledgedRef = useRef(new Set<string>())
  const deliveryReceiptPendingRef = useRef(new Set<string>())
  const [queueFullShowLeaveMessageButton, setQueueFullShowLeaveMessageButton] = useState(true)
  const [queueFullLeaveMessageButtonLabel, setQueueFullLeaveMessageButtonLabel] = useState('')
  // When a bot→human handoff overflows the queue, surface an inline confirm-style
  // card (leave message / keep chatting) instead of the full-screen overflow card.
  const [handoffQueueFullInline, setHandoffQueueFullInline] = useState(false)
  const [currentQueueCount, setCurrentQueueCount] = useState<number | null>(null)
  const [conversationInitializing, setConversationInitializing] = useState(true)
  const [messageSoundEnabled, setMessageSoundEnabled] = useState(true)
  const [embedReadyPosted, setEmbedReadyPosted] = useState(false)
  const [embedInitPayload, setEmbedInitPayload] = useState<EmbedInitPayload | null>(
    () => embedInitRequired ? null : standaloneInitPayload,
  )
  const [embedActivated, setEmbedActivated] = useState(
    () => !embedActivationRequired,
  )
  const [embedComposerFocusRequest, setEmbedComposerFocusRequest] = useState(0)
  const [embedInitGraceElapsed, setEmbedInitGraceElapsed] = useState(false)
  const startedRef = useRef(false)
  const customerReadInFlightRef = useRef<Set<string>>(new Set())
  const lastCustomerReadMessageRef = useRef<string | null>(null)
  const readReceiptConfirmedIdsRef = useRef<Map<string, Set<number>>>(new Map())
  const readReceiptInFlightKeysRef = useRef<Set<string>>(new Set())
  const historyReadReceiptSentRef = useRef<Set<string>>(new Set())
  const historyReadReceiptPendingRef = useRef<Set<string>>(new Set())
  const readReceiptRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const conversationPublicIdRef = useRef<string | null>(null)
  const handledMessageAlertNonceRef = useRef<number | null>(null)
  const prevLastMessageIdRef = useRef<number | null>(null)
  const prevConversationStatusRef = useRef<string | null>(null)
  // Offline UI is driven purely by the server's start_conversation response so
  // that a visitor with an unfinished conversation can always re-enter it,
  // regardless of whether any agent is currently online. The channel-level
  // availability hint is kept only as a fallback copy for the offline screen.
  const isFormMessage = leaveMessageMode && channel?.config.leave_message_mode === 'form'
  const isLeaveMessage = leaveMessageMode && (!conversationPublicId || isFormMessage)
  const queueFull = !!queueFullMessage && !isLeaveMessage && !startConversationError && !handoffQueueFullInline
  const isOffline = !!socketOfflineMessage && !conversationPublicId && !isLeaveMessage && !queueFull && !handoffQueueFullInline && !startConversationError

  useEffect(() => {
    conversationPublicIdRef.current = conversationPublicId
  }, [conversationPublicId])

  useEffect(() => {
    setMessageSoundEnabled(readVisitorMessageAlertEnabled())
    return bindVisitorMessageAlertUnlock()
  }, [])

  useEffect(() => {
    initTestEventChannel()
  }, [])

  useEffect(() => {
    if (messages.length === 0) return
    const last = messages[messages.length - 1]
    if (last.id === prevLastMessageIdRef.current) return
    prevLastMessageIdRef.current = last.id
    emitTestEvent('message:received', {
      message_id: last.id,
      sender_type: last.sender_type,
      content_type: last.content_type,
    })
  }, [messages])

  useEffect(() => {
    const from = prevConversationStatusRef.current
    const to = conversationStatus
    if (from === to) return
    prevConversationStatusRef.current = to
    emitTestEvent('status:changed', { from, to })
    if (from && (from === 'bot' || from === 'handoff_pending')) {
      if (to === 'active') {
        emitTestEvent('handoff:completed', { result: 'agent' })
      } else if (to === 'queued') {
        emitTestEvent('handoff:completed', { result: 'queued' })
      }
    }
  }, [conversationStatus])

  useEffect(() => {
    if (handledMessageAlertNonceRef.current === null) {
      handledMessageAlertNonceRef.current = messageAlertNonce
      return
    }
    if (handledMessageAlertNonceRef.current === messageAlertNonce) return

    handledMessageAlertNonceRef.current = messageAlertNonce
    if (messageSoundEnabled) playVisitorMessageAlert()
  }, [messageAlertNonce, messageSoundEnabled])

  const handleMessageSoundEnabledChange = useCallback((enabled: boolean) => {
    setMessageSoundEnabled(enabled)
    setVisitorMessageAlertEnabled(enabled)
    if (enabled) {
      unlockVisitorMessageAlert()
    } else {
      stopVisitorMessageAlert()
    }
  }, [])

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
    setEmbedComposerFocusRequest(0)
    setEmbedInitGraceElapsed(false)
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

      // Every frame message carries the SDK's current (possibly null) token, so a
      // null value alone can't mean logout. Only the SDK's explicit clear flag does.
      const explicitLogout =
        data.type === 'update_context' && data.contextTokenCleared === true
      const nextPayload = sanitizeEmbedPayload(data, {
        allowExplicitNullToken: explicitLogout,
      })
      if (data.type === 'update_context') {
        if (explicitLogout && channelKey) {
          clearVisitorCredential(channelKey)
        }
        setEmbedInitPayload((current) => ({
          ...(current ?? EMPTY_EMBED_INIT_PAYLOAD),
          ...nextPayload,
          initSource: 'sdk',
        }))
      } else {
        // init/open: first identity-bearing payload wins, but an empty 3s
        // timeout fallback must not block a later SDK init that carries contextToken.
        setEmbedInitPayload((current) => mergeEmbedInitPayload(current, nextPayload))
      }
      const shouldActivate = data.type === 'open' || data.active === true || data.preload !== true
      if (shouldActivate) {
        setEmbedActivated(true)
      }
      if (data.type === 'open' || (data.type === 'init' && data.active === true)) {
        setEmbedComposerFocusRequest((value) => value + 1)
      }
    }

    window.addEventListener('message', handleMessage)
    return () => {
      window.removeEventListener('message', handleMessage)
    }
  }, [channelKey, embedInitRequired, embedInstanceId])

  useEffect(() => {
    if (!embedInitRequired || !embedReadyPosted || !embedActivated || embedInitPayload !== null) return
    const timer = window.setTimeout(() => {
      setEmbedInitPayload((current) => current ?? { initSource: 'timeout' })
    }, EMBED_INIT_FALLBACK_MS)
    return () => window.clearTimeout(timer)
  }, [embedActivated, embedInitPayload, embedInitRequired, embedReadyPosted])

  // The identity-less fallback holds off on opening a conversation so a late SDK
  // `init` can supply contextToken first. If nothing arrives, open it anyway.
  useEffect(() => {
    if (embedInitPayload?.initSource !== 'timeout' || embedInitGraceElapsed) return
    const timer = window.setTimeout(() => setEmbedInitGraceElapsed(true), EMBED_INIT_GRACE_MS)
    return () => window.clearTimeout(timer)
  }, [embedInitGraceElapsed, embedInitPayload])

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
    if (!channelKey || !channelLoaded || !embedActivated || (embedInitRequired && embedInitPayload === null)) return
    const embedPayload = embedInitPayload ?? EMPTY_EMBED_INIT_PAYLOAD
    const embedVisitor = embedPayload.visitor
    const currentContextToken = embedPayload.contextToken || null
    const visitorPayloadKey = getVisitorPayloadKey(embedPayload)

    setVisitorExternalId(null)
    setVisitorSessionToken(null)
    setConversationPublicId(null)
    setOfflineMessagePublicId(null)
    setOfflineMessageSource(null)
    setOfflineMessageQueueTarget(null)
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
      if (embedPayload.contextToken === null) {
        clearVisitorCredential(channelKey)
      }
      const stored = readVisitorCredential(channelKey)
      const storedForRenewal = selectStoredVisitorCredential(stored, embedPayload)
      const storedToken = storedForRenewal?.visitorSessionToken
      const storedSessionExpiresAt = storedForRenewal?.visitorSessionExpiresAt
      const canReuseStoredToken =
        typeof storedToken === 'string' &&
        typeof storedSessionExpiresAt === 'number' &&
        storedSessionExpiresAt > Date.now() + 60 * 1000

      if (storedForRenewal && canReuseStoredToken) {
        return {
          session: {
            visitor_external_id: storedForRenewal.visitorExternalId,
            visitor_session_token: storedToken,
            visitor_secret: storedForRenewal.visitorSecret,
            expires_in: Math.max(
              0,
              Math.floor((storedSessionExpiresAt - Date.now()) / 1000),
            ),
          },
          stored: storedForRenewal,
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
            identity_source: resolveVisitorIdentitySource({
              reused,
              hadStoredCredential: Boolean(stored),
              hasContextToken: Boolean(currentContextToken),
            }),
            init_source: embedPayload.initSource || 'standalone',
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
    channelLoaded,
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
      ...((preferredLocale || (typeof navigator !== 'undefined' ? navigator.language : ''))
        ? { locale: preferredLocale || navigator.language }
        : {}),
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
          queue_type?: string
          queue_id?: number | null
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
            setOfflineMessageSource(null)
            setOfflineMessageQueueTarget(null)
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
              reconcileConversationMessages(
                res.conversation.conversation_public_id,
                currentMessages,
              )
              setHasMore(data.has_more)
              if (
                res.conversation.status === 'handoff_pending'
                && channel?.config.open_agent_handoff_behavior === 'confirm'
              ) {
                setPendingHumanHandoff(restorePendingHumanHandoff(currentMessages, locale))
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
            setOfflineMessageSource(null)
            setOfflineMessageQueueTarget(null)
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
              || t('chat.restricted.title', locale),
            )
            setSocketOfflineMessage(
              res.restricted_service_message
              || channel?.config.restricted_service_message
              || t('chat.restricted.message', locale),
            )
          } else if (res.error === 'OFFLINE') {
            trackEvent('conversation_start_offline', {
              props: { reason: res.reason || 'offline' },
              metrics: { duration_ms: Date.now() - startedAt },
            })
            setConversationPublicId(null)
            setOfflineMessagePublicId(null)
            setOfflineMessageSource(null)
            setOfflineMessageQueueTarget(null)
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
            setOfflineMessageSource(null)
            setOfflineMessageQueueTarget(null)
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
                setOfflineMessageSource(null)
                setOfflineMessageQueueTarget(null)
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
              setOfflineMessageSource(null)
              setOfflineMessageQueueTarget(null)
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
            setOfflineMessageSource(null)
            setOfflineMessageQueueTarget(null)
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
            setOfflineMessageSource(null)
            setOfflineMessageQueueTarget(queueTargetFromPayload(res))
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
            setHandoffQueueFullInline(false)
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
    preferredLocale,
    socket,
    connected,
    conversationPublicId,
    setConversationPublicId,
    reconcileConversationMessages,
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

  const deliveryReceiptBatches = useMemo(
    () => buildMessageDeliveryBatches([
      { conversationPublicId, messages },
      ...historyConversations.map((item) => ({
        conversationPublicId: item.conversation_public_id,
        messages: item.messages,
      })),
      ...unreadReplyConversations.map((item) => ({
        conversationPublicId: item.conversation_public_id,
        messages: item.messages,
      })),
    ]),
    [conversationPublicId, historyConversations, messages, unreadReplyConversations],
  )

  useEffect(() => {
    if (!socket || !connected) return

    for (const batch of deliveryReceiptBatches) {
      const pendingIds = batch.messageIds.filter((messageId) => {
        const key = `${batch.conversationPublicId}:${messageId}`
        return !deliveryReceiptAcknowledgedRef.current.has(key)
          && !deliveryReceiptPendingRef.current.has(key)
      })
      if (pendingIds.length === 0) continue

      const keys = pendingIds.map((messageId) => `${batch.conversationPublicId}:${messageId}`)
      keys.forEach((key) => deliveryReceiptPendingRef.current.add(key))
      socket.timeout(READ_RECEIPT_ACK_TIMEOUT_MS).emit(
        'messages_delivered',
        {
          conversation_public_id: batch.conversationPublicId,
          message_ids: pendingIds,
        },
        (error: Error | null, response?: MarkReadAck) => {
          keys.forEach((key) => deliveryReceiptPendingRef.current.delete(key))
          if (error || response?.ok === false) {
            scheduleReadReceiptRetry()
            return
          }
          keys.forEach((key) => deliveryReceiptAcknowledgedRef.current.add(key))
        },
      )
    }
  }, [connected, deliveryReceiptBatches, readReceiptVisibilityNonce, scheduleReadReceiptRetry, socket])

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

  // Conversations shown inline (unread replies / loaded history) that still
  // contain agent messages the visitor has not read. Once these blocks are
  // displayed, mark them read so agents get the read receipt.
  const inlineUnreadConversationIds = useMemo(() => {
    const ids = new Set<string>()
    for (const item of [...unreadReplyConversations, ...historyConversations]) {
      if (
        item.conversation_public_id !== conversationPublicId
        && (item.agent_unread_message_ids?.length ?? 0) > 0
      ) {
        ids.add(item.conversation_public_id)
      }
    }
    return Array.from(ids)
  }, [conversationPublicId, historyConversations, unreadReplyConversations])

  useEffect(() => {
    if (!socket || !connected || inlineUnreadConversationIds.length === 0) return
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return

    for (const inlineConversationId of inlineUnreadConversationIds) {
      if (
        historyReadReceiptSentRef.current.has(inlineConversationId)
        || historyReadReceiptPendingRef.current.has(inlineConversationId)
      ) {
        continue
      }
      historyReadReceiptPendingRef.current.add(inlineConversationId)
      socket.timeout(READ_RECEIPT_ACK_TIMEOUT_MS).emit(
        'mark_read',
        { conversation_public_id: inlineConversationId },
        (error: Error | null, response?: MarkReadAck) => {
          historyReadReceiptPendingRef.current.delete(inlineConversationId)
          if (error || response?.ok === false) {
            scheduleReadReceiptRetry()
            return
          }
          historyReadReceiptSentRef.current.add(inlineConversationId)
        },
      )
    }
  }, [
    connected,
    inlineUnreadConversationIds,
    readReceiptVisibilityNonce,
    scheduleReadReceiptRetry,
    socket,
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

  const handleOfflineMessageCreated = useCallback((offlineMessagePublicId: string) => {
    setOfflineMessagePublicId(offlineMessagePublicId)
    setOfflineMessageSource(null)
    setOfflineMessageQueueTarget(null)
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
    setOfflineMessageSource(null)
    setOfflineMessageQueueTarget(null)
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
    setHandoffQueueFullInline(false)
    setCurrentQueueCount(null)
    setSocketOfflineTitle('')
    setSocketOfflineMessage('')
    if (channel?.config.leave_message_mode !== 'form') setConversationPublicId(null)
    setOfflineMessagePublicId(null)
    setOfflineMessageSource('queue_full')
    setLeaveMessageMode(true)
    setLeaveMessagePrompt((current) => current || channel?.config.leave_message_prompt || '')
    if (channel?.config.leave_message_mode !== 'form') {
      setMessages([])
      setHasMore(false)
    }
    setEnded(false)
    if (channel?.config.leave_message_mode !== 'form') setConversationStatus(null)
  }, [channel?.config.leave_message_mode, channel?.config.leave_message_prompt, setConversationPublicId, setHasMore, setMessages])

  const handleQueueLeaveMessage = useCallback(async () => {
    if (!conversationPublicId || !visitorSessionToken || queueLeaveMessageLoading) return
    setQueueLeaveMessageLoading(true)
    try {
      const result = await leaveQueuedConversationMessage({
        conversationPublicId,
        visitorSessionToken,
      })
      setQueueFullMessage('')
      setQueueFullShowLeaveMessageButton(true)
      setQueueFullLeaveMessageButtonLabel('')
      setHandoffQueueFullInline(false)
      setCurrentQueueCount(null)
      setSocketOfflineTitle('')
      setSocketOfflineMessage('')
      if (!result.deferred) setConversationPublicId(null)
      setOfflineMessagePublicId(null)
      setOfflineMessageSource(result.source)
      setOfflineMessageQueueTarget({
        queueType: result.queue_type,
        queueId: result.queue_id,
      })
      setLeaveMessageMode(true)
      setLeaveMessagePrompt(result.leave_message_prompt || channel?.config.leave_message_prompt || '')
      if (!result.deferred) {
        setMessages([])
        setHasMore(false)
      }
      setEnded(false)
      if (!result.deferred) setConversationStatus(null)
    } catch {
      window.alert(t('chat.leaveMessage.unavailable', locale))
    } finally {
      setQueueLeaveMessageLoading(false)
    }
  }, [
    channel?.config.leave_message_prompt,
    conversationPublicId,
    locale,
    queueLeaveMessageLoading,
    setConversationPublicId,
    setHasMore,
    setMessages,
    visitorSessionToken,
  ])

  // Visitor declined the leave-message option on queue overflow and stays with
  // the bot. Clear the overflow card and keep the existing bot conversation.
  const handleHandoffQueueFullContinueBot = useCallback(() => {
    setQueueFullMessage('')
    setQueueFullShowLeaveMessageButton(true)
    setQueueFullLeaveMessageButtonLabel('')
    setHandoffQueueFullInline(false)
    setOfflineMessageSource(null)
    setOfflineMessageQueueTarget(null)
    setCurrentQueueCount(null)
  }, [])

  const handleHandoffLeaveMessage = useCallback((prompt?: string) => {
    emitTestEvent('handoff:completed', { result: 'leave_message' })
    setQueueFullMessage('')
    setQueueFullShowLeaveMessageButton(true)
    setQueueFullLeaveMessageButtonLabel('')
    setHandoffQueueFullInline(false)
    setCurrentQueueCount(null)
    setSocketOfflineTitle('')
    setSocketOfflineMessage('')
    if (channel?.config.leave_message_mode !== 'form') setConversationPublicId(null)
    setOfflineMessagePublicId(null)
    setOfflineMessageSource(null)
    setOfflineMessageQueueTarget(null)
    setLeaveMessageMode(true)
    setLeaveMessagePrompt(prompt || channel?.config.leave_message_prompt || '')
    if (channel?.config.leave_message_mode !== 'form') {
      setMessages([])
      setHasMore(false)
    }
    setEnded(false)
    if (channel?.config.leave_message_mode !== 'form') setConversationStatus(null)
    setPendingHumanHandoff(null)
  }, [
    channel?.config.leave_message_mode,
    channel?.config.leave_message_prompt,
    setConversationPublicId,
    setHasMore,
    setMessages,
    setPendingHumanHandoff,
  ])

  const handleContinueBotFromForm = useCallback(() => {
    setLeaveMessageMode(false)
    setOfflineMessageSource(null)
    setOfflineMessageQueueTarget(null)
    setLeaveMessagePrompt('')
    setQueueFullMessage('')
    setHandoffQueueFullInline(false)
  }, [])

  const handleHandoffQueueFull = useCallback((payload: {
    queue_full_message?: string
    queue_full_show_leave_message_button?: boolean
    queue_full_leave_message_button_label?: string
    leave_message_prompt?: string
    queue_type?: string
    queue_id?: number | null
  }, inline = false) => {
    setSocketOfflineTitle('')
    setSocketOfflineMessage('')
    setCurrentQueueCount(null)
    setOfflineMessageSource(null)
    setOfflineMessageQueueTarget(queueTargetFromPayload(payload))
    setLeaveMessageMode(false)
    setLeaveMessagePrompt(payload.leave_message_prompt || channel?.config.leave_message_prompt || '')
    setQueueFullMessage(payload.queue_full_message || channel?.config.queue_full_message || '')
    setQueueFullShowLeaveMessageButton(payload.queue_full_show_leave_message_button !== false)
    setQueueFullLeaveMessageButtonLabel(
      payload.queue_full_leave_message_button_label
      || channel?.config.queue_full_leave_message_button_label
      || '',
    )
    setHandoffQueueFullInline(inline)
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
    if (embedPayload.contextToken === null) {
      clearVisitorCredential(channelKey)
    }
    const storedForRenewal = selectStoredVisitorCredential(
      readVisitorCredential(channelKey),
      embedPayload,
    )

    createVisitorSession({
      channelKey,
      visitorExternalId: storedForRenewal?.visitorExternalId,
      visitorSecret: storedForRenewal?.visitorSecret,
      visitorName: embedPayload.visitor?.name,
      metadata: embedPayload.visitor?.metadata,
      contextToken: embedPayload.contextToken || null,
    })
      .then((session) => {
        if (cancelled) return
        const visitorSecret = session.visitor_secret || storedForRenewal?.visitorSecret
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
    // The identity-less fallback waits out the grace period first: a late SDK
    // init with contextToken would otherwise create a second conversation.
    const embedPayload = embedInitPayload ?? EMPTY_EMBED_INIT_PAYLOAD
    if (!shouldAutoStartConversation(embedPayload, embedInitGraceElapsed)) return
    startedRef.current = true
    void startConversation()
  }, [
    socket,
    connected,
    embedActivated,
    embedInitPayload,
    embedInitGraceElapsed,
    startConversation,
    unreadReplyChecked,
    ended,
  ])

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

  // Room membership belongs to a concrete Socket.IO connection. Re-establish it
  // whenever either the active conversation or the underlying connection changes.
  useEffect(() => {
    if (!socket || !connected || !conversationPublicId || !visitorSessionToken) {
      setConversationSubscriptionStatus('idle')
      return
    }

    let cancelled = false
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    const permanentErrors = new Set([
      'NOT_FOUND',
      'UNAUTHORIZED',
      'FORBIDDEN',
      'visitor_session_required',
    ])

    const reconcileMessages = () => {
      fetchPublicMessages({
        conversationPublicId,
        visitorSessionToken,
        limit: 50,
      })
        .then((res) => {
          if (cancelled) return
          reconcileConversationMessages(
            conversationPublicId,
            res.items.map(mapPublicMessage),
          )
          setHasMore(res.has_more)
        })
        .catch(() => {
          if (cancelled) return
          trackEvent('conversation_messages_load_failed', {
            level: 'warn',
            conversation_external_id: conversationPublicId,
            props: { source: 'conversation_subscription' },
          })
        })
    }

    const join = (attempt: number) => {
      if (cancelled || !socket.connected) return
      setConversationSubscriptionStatus('joining')
      socket.timeout(CONVERSATION_JOIN_ACK_TIMEOUT_MS).emit(
        'join_conversation',
        { conversation_public_id: conversationPublicId },
        (timeoutError: Error | null, response?: JoinConversationAck) => {
          if (cancelled) return
          if (!timeoutError && response?.ok === true) {
            setConversationSubscriptionStatus('joined')
            trackEvent('conversation_subscription_succeeded', {
              conversation_external_id: conversationPublicId,
              props: { attempt: attempt + 1, connection_epoch: connectionEpoch },
            })
            reconcileMessages()
            return
          }

          const error = response?.error || timeoutError?.message || 'unknown'
          const nextAttempt = attempt + 1
          if (
            permanentErrors.has(error)
            || nextAttempt >= CONVERSATION_JOIN_RETRY_DELAYS_MS.length
          ) {
            setConversationSubscriptionStatus('degraded')
            trackEvent('conversation_subscription_failed', {
              level: 'error',
              conversation_external_id: conversationPublicId,
              props: {
                error,
                attempts: nextAttempt,
                connection_epoch: connectionEpoch,
              },
            })
            return
          }

          trackEvent('conversation_subscription_retry', {
            level: 'warn',
            conversation_external_id: conversationPublicId,
            props: { error, attempt: nextAttempt + 1 },
          })
          retryTimer = setTimeout(
            () => join(nextAttempt),
            CONVERSATION_JOIN_RETRY_DELAYS_MS[nextAttempt],
          )
        },
      )
    }

    join(0)
    return () => {
      cancelled = true
      if (retryTimer) clearTimeout(retryTimer)
    }
  }, [
    connected,
    connectionEpoch,
    conversationPublicId,
    conversationSubscriptionRetryNonce,
    reconcileConversationMessages,
    setHasMore,
    socket,
    trackEvent,
    visitorSessionToken,
  ])

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
      const convertedConversationPublicId = data.conversation_public_id
      if (!convertedConversationPublicId) return
      if (
        offlineMessagePublicId
        && data.offline_message_public_id
        && data.offline_message_public_id !== offlineMessagePublicId
      ) {
        return
      }
      setOfflineMessagePublicId(null)
      setOfflineMessageSource(null)
      setOfflineMessageQueueTarget(null)
      setLeaveMessageMode(false)
      setLeaveMessagePrompt('')
      setSocketOfflineTitle('')
      setSocketOfflineMessage('')
      setQueueFullMessage('')
      setQueueFullShowLeaveMessageButton(true)
      setQueueFullLeaveMessageButtonLabel('')
      setHandoffQueueFullInline(false)
      setCurrentQueueCount(null)
      setConversationPublicId(convertedConversationPublicId)
      setConversationStatus(data.status || 'active')
      setEnded(false)
      trackEvent('offline_message_conversation_created', {
        conversation_external_id: convertedConversationPublicId,
        props: { status: data.status || 'active' },
      })
      fetchPublicMessages({
        conversationPublicId: convertedConversationPublicId,
        visitorSessionToken,
        limit: 50,
      })
        .then((res) => {
          reconcileConversationMessages(
            convertedConversationPublicId,
            res.items.map(mapPublicMessage),
          )
          setHasMore(res.has_more)
        })
        .catch(() => {
          trackEvent('conversation_messages_load_failed', {
            level: 'warn',
            conversation_external_id: convertedConversationPublicId,
            props: { source: 'offline_message_conversion' },
          })
        })
    }
    socket.on('offline_message_conversation_created', handler)
    return () => {
      socket.off('offline_message_conversation_created', handler)
    }
  }, [
    offlineMessagePublicId,
    reconcileConversationMessages,
    setConversationPublicId,
    setHasMore,
    socket,
    trackEvent,
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
  const showSubscriptionRecovery = Boolean(
    socket
    && connected
    && conversationPublicId
    && conversationSubscriptionStatus === 'degraded',
  )
  const showAssistPanel = Boolean(
    !isEmbed
    && !isMobile
    && config.assist_panel_enabled
    && config.assist_panel_react_code?.trim(),
  )
  const historyAvailable = channel?.has_conversation_history === true || historyConversations.length > 0
  const formMessageSource: FormMessageSource = offlineMessageSource
    ?? (conversationPublicId ? 'bot_handoff' : 'outside_service_hours')

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
            {t('chat.invalidLink', locale)}
          </p>
        </div>
        <LegalFooter locale={locale} compact />
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
              messageSoundEnabled={messageSoundEnabled}
              onMessageSoundEnabledChange={handleMessageSoundEnabledChange}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center">
              <IconLoader2 size={32} className="animate-spin text-muted-foreground" />
            </div>
          )}
        </div>
        <LegalFooter locale={locale} compact />
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
            {t('chat.invalidLink', locale)}
          </p>
        </div>
        <LegalFooter locale={locale} compact />
      </div>
    )
  }

  return (
    <div className={pageShellClassName} style={pageShellStyle}>
      {/* ── Connection status bar ── */}
      {showConnectionStatus && (
        <div className="absolute left-0 right-0 top-0 z-50 border-b border-amber-200/50 bg-[#f4ebd4] px-4 py-1 text-center text-xs text-stone-800">
          {t('chat.connection.reconnecting', locale)}
        </div>
      )}
      {showSubscriptionRecovery && (
        <div className="absolute left-0 right-0 top-0 z-50 border-b border-amber-200/50 bg-[#f4ebd4] px-4 py-1 text-center text-xs text-stone-800">
          {t('chat.connection.failed', locale)}{' '}
          <button
            type="button"
            className="font-medium underline underline-offset-2"
            onClick={() => setConversationSubscriptionRetryNonce((value) => value + 1)}
          >
            {t('chat.connection.retry', locale)}
          </button>
        </div>
      )}

      {/* ── Chat container (backed by assistant-ui runtime) ── */}
      {isFormMessage ? (
        <div className={chatContainerClassName}>
          <ChatHeader
            channel={channel}
            isMobile={isMobile}
            isEmbed={isEmbed}
            onEmbedClose={handleEmbedClose}
            locale={locale}
            messageSoundEnabled={messageSoundEnabled}
            onMessageSoundEnabledChange={handleMessageSoundEnabledChange}
          />
          <FormMessage
            visitorSessionToken={visitorSessionToken}
            locale={locale}
            source={formMessageSource}
            conversationPublicId={conversationPublicId}
            queueType={offlineMessageQueueTarget?.queueType}
            queueId={offlineMessageQueueTarget?.queueId}
            onContinueConversation={
              conversationPublicId
              && (conversationStatus === 'bot' || conversationStatus === 'handoff_pending')
                ? handleContinueBotFromForm
                : undefined
            }
          />
        </div>
      ) : showAssistPanel ? (
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
          offlineMessageSource={offlineMessageSource}
          offlineMessageQueueTarget={offlineMessageQueueTarget}
          queueFull={queueFull}
          queueFullMessage={queueFullMessage}
          queueFullShowLeaveMessageButton={queueFullShowLeaveMessageButton}
          queueFullLeaveMessageButtonLabel={queueFullLeaveMessageButtonLabel}
          queueLeaveMessageLoading={queueLeaveMessageLoading}
          handoffQueueFullInline={handoffQueueFullInline}
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
          onQueueLeaveMessage={handleQueueLeaveMessage}
          onHandoffQueueFullContinueBot={handleHandoffQueueFullContinueBot}
          onHandoffLeaveMessage={handleHandoffLeaveMessage}
          onHandoffQueueFull={handleHandoffQueueFull}
          onConversationStatusChange={setConversationStatus}
          onCurrentQueueCountChange={setCurrentQueueCount}
          onOfflineMessageCreated={handleOfflineMessageCreated}
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
                locale={locale}
                messageSoundEnabled={messageSoundEnabled}
                onMessageSoundEnabledChange={handleMessageSoundEnabledChange}
              />
              <div className="flex min-h-0 flex-1">
                <div className="flex min-h-0 min-w-[480px] flex-1 flex-col overflow-hidden">
                  <VisitorThread
                    offlineTitle={isOffline ? offlineTitle : undefined}
                    offlineMessage={isOffline ? offlineMessage : undefined}
                    isEmbed={isEmbed}
                    showHeader={false}
                    onEmbedClose={handleEmbedClose}
                    composerFocusRequest={embedComposerFocusRequest}
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
            offlineMessageSource={offlineMessageSource}
            offlineMessageQueueTarget={offlineMessageQueueTarget}
            queueFull={queueFull}
            queueFullMessage={queueFullMessage}
            queueFullShowLeaveMessageButton={queueFullShowLeaveMessageButton}
            queueFullLeaveMessageButtonLabel={queueFullLeaveMessageButtonLabel}
            queueLeaveMessageLoading={queueLeaveMessageLoading}
            handoffQueueFullInline={handoffQueueFullInline}
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
            onQueueLeaveMessage={handleQueueLeaveMessage}
            onHandoffQueueFullContinueBot={handleHandoffQueueFullContinueBot}
            onHandoffLeaveMessage={handleHandoffLeaveMessage}
            onHandoffQueueFull={handleHandoffQueueFull}
            onConversationStatusChange={setConversationStatus}
            onCurrentQueueCountChange={setCurrentQueueCount}
            onOfflineMessageCreated={handleOfflineMessageCreated}
            onSatisfactionInitiate={handleSatisfactionInitiate}
            onSatisfactionSubmitted={handleSatisfactionSubmitted}
          >
            <VisitorThread
              offlineTitle={isOffline ? offlineTitle : undefined}
              offlineMessage={isOffline ? offlineMessage : undefined}
              isEmbed={isEmbed}
              onEmbedClose={handleEmbedClose}
              composerFocusRequest={embedComposerFocusRequest}
              messageSoundEnabled={messageSoundEnabled}
              onMessageSoundEnabledChange={handleMessageSoundEnabledChange}
            />
          </VisitorChatRuntimeProvider>
        </div>
      )}

      {/* AGPL §13: visitors interacting with this network service must be
          offered the Corresponding Source. Compact variant keeps the chat UX
          uncluttered on both mobile and desktop. */}
      <LegalFooter locale={locale} compact />
    </div>
  )
}
