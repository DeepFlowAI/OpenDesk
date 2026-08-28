'use client'

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { ThreadPrimitive, type MessageState } from '@assistant-ui/react'
import {
  useVisitorChatConfig,
  isOpenAgentMessageStreaming,
  type VisitorMessageMeta,
} from './visitor-chat-runtime'
import { useVisitorChatStore } from '@/context/visitor-chat-store'
import { ChatHeader } from '@/app/components/features/visitor-chat/chat-header'
import {
  MessageBubble,
  shouldShowVisitorRecalledNotice,
} from '@/app/components/features/visitor-chat/message-bubble'
import { SystemMessage } from '@/app/components/features/visitor-chat/system-message'
import { resolveVisitorSystemEventContent } from '@/lib/workspace-agent-display'
import {
  isVisitorQueueEnteredContent,
  isVisitorQueueEnteredMessage,
} from '@/lib/visitor-queue-notice'
import {
  HandoffQueueFullCard,
  HumanHandoffEventMessage,
  collectConfirmedHandoffToolCallIds,
  isOpenAgentHandoffEventMessage,
  resolveHandoffConfirmCardState,
  resolveHandoffEventType,
} from '@/app/components/features/visitor-chat/human-handoff-event-message'
import {
  OpenAgentFAQMessage,
  OpenAgentWelcomeMessage,
  WelcomeMessage,
} from '@/app/components/features/visitor-chat/welcome-message'
import { SafeHtml } from '@/components/safe-html'
import { TypingIndicator } from '@/app/components/features/visitor-chat/typing-indicator'
import { VisitorComposer, type VisitorComposerInsertRequest } from './visitor-composer'
import { IconLoader2, IconArrowDown, IconAlertCircle, IconStar, IconX } from '@tabler/icons-react'
import { SatisfactionSurveyModal } from '@/app/components/features/satisfaction-survey-modal'
import { VisitorAnnouncement } from '@/app/components/features/visitor-chat/announcement'
import { submitPublicSatisfaction } from '@/service/use-satisfaction-survey'
import { isLeaveMessagePromptMessage, leaveMessagePromptToPlainText } from '@/lib/offline-message-event'
import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type { SatisfactionSubmissionPayload } from '@/models/satisfaction-survey'
import type {
  Message,
  VisitorConversationHistoryItem,
  VisitorUnreadOfflineReplyItem,
} from '@/models/conversation'
import {
  getAgentAvatarUrl,
  getOpenAgentAvatarUrl,
  shouldShowAgentAvatar,
  shouldShowAssistantAvatar,
} from '@/app/components/features/visitor-chat/avatar'
import {
  getOpenAgentWelcomeBlocksFromMetadata,
  getValidOpenAgentFAQ,
  isValidOpenAgentWelcomeBlock,
} from '@/lib/open-agent-welcome-message'
import { isWelcomeLikeContentType } from '@/lib/welcome-message-content-type'
import { formatMessageTime } from '@/lib/message-time'

function shouldShowTimestamp(cur: Message, prev: Message | null): boolean {
  if (!prev) return true
  return new Date(cur.created_at).getTime() - new Date(prev.created_at).getTime() > 5 * 60 * 1000
}

function shouldShowName(cur: Message, prev: Message | null): boolean {
  if (!prev) return true
  return prev.sender_type !== cur.sender_type || prev.sender_id !== cur.sender_id
}

function shouldShowAvatar(cur: Message, next: Message | null): boolean {
  if (!next) return true
  return next.sender_type !== cur.sender_type
}

function visitorMessageDomAttrs(
  msg: Pick<Message, 'id' | 'sender_type' | 'status' | 'metadata'>,
  options?: { messageStatus?: string },
) {
  const messageStatus = options?.messageStatus ?? msg.status
  return {
    'data-visitor-message-id': msg.id,
    'data-sender-type': msg.sender_type,
    ...(messageStatus ? { 'data-message-status': messageStatus } : {}),
    ...(msg.sender_type === 'bot'
      ? { 'data-agent-streaming': isOpenAgentMessageStreaming(msg.metadata) ? 'true' : 'false' }
      : {}),
  }
}

function isCurrentNavigationReload(): boolean {
  if (typeof performance === 'undefined') return false
  const nav = performance.getEntriesByType('navigation')[0]
  return Boolean(nav && 'type' in nav && (nav as PerformanceNavigationTiming).type === 'reload')
}

// ─── Reconstruct a Message object from assistant-ui state ───────

function toOriginalMessage(
  message: MessageState,
  meta: VisitorMessageMeta | undefined,
): Message {
  const content = message.content
    ?.map((part) => {
      if (part.type === 'text' && 'text' in part) return part.text as string
      if (part.type === 'image' && 'image' in part) return part.image as string
      return ''
    })
    .join('') || ''

  const metadata: Record<string, unknown> = { ...(meta?.metadata || {}) }
  if (meta?.streaming) metadata.streaming = true
  if (meta?.eventType) metadata.event_type = meta.eventType
  if (meta?.handoffPayload) metadata.handoff_payload = meta.handoffPayload
  const thinkingBlocks = meta?.openAgentThinkingBlocks || []
  if (thinkingBlocks.length > 0) metadata.open_agent_thinking_blocks = thinkingBlocks
  const toolBlocks = meta?.openAgentToolBlocks || []
  if (toolBlocks.length > 0) metadata.open_agent_tool_blocks = toolBlocks
  const textBlocks = meta?.openAgentTextBlocks || []
  if (textBlocks.length > 0) metadata.open_agent_text_blocks = textBlocks

  return {
    id: Number(message.id) || 0,
    conversation_id: 0,
    conversation_public_id: meta?.conversationPublicId,
    sender_type: (meta?.senderType || (message.role === 'user' ? 'visitor' : 'agent')) as Message['sender_type'],
    sender_id: meta?.senderId ?? null,
    sender_name: meta?.senderName ?? null,
    sender_avatar: meta?.senderAvatar ?? null,
    content_type: (meta?.contentType || 'text') as Message['content_type'],
    content,
    is_recalled: meta?.isRecalled || meta?.metadata?.is_recalled === true,
    recalled_at: meta?.recalledAt ?? null,
    recalled_by_type: meta?.recalledByType ?? null,
    recalled_by_id: meta?.recalledById ?? null,
    recalled_by_name: meta?.recalledByName ?? null,
    metadata: Object.keys(metadata).length > 0 ? metadata : undefined,
    created_at: message.createdAt?.toISOString() || new Date().toISOString(),
  }
}

function ConversationDivider({
  label,
  unreadLabel,
}: {
  label: string
  unreadLabel?: string | null
}) {
  return (
    <div className="flex items-center gap-3 px-5 py-2 text-xs text-muted-foreground">
      <div className="h-px flex-1 bg-border" />
      <span className="shrink-0">{label}</span>
      {unreadLabel && (
        <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-foreground">
          {unreadLabel}
        </span>
      )}
      <div className="h-px flex-1 bg-border" />
    </div>
  )
}

function renderQueueMessage(html: string, currentQueueCount: number | null): string {
  const value = currentQueueCount == null ? '-' : String(currentQueueCount)
  return html.replaceAll('{{current_queue_count}}', value)
}

const OLD_DEFAULT_QUEUE_MESSAGE = '当前咨询人数较多，您正在排队中，当前排队数：{{current_queue_count}}。请稍候，我们会尽快为您接入客服。'
const DEFAULT_QUEUE_MESSAGE = '您已进入人工客服队列。当前排队人数：{{current_queue_count}} 位，请稍候。客服接入后会立即回复您。'
function isDefaultQueueMessage(html: string): boolean {
  const value = html.trim()
  return !value || value === OLD_DEFAULT_QUEUE_MESSAGE || value === DEFAULT_QUEUE_MESSAGE
}

function displaySystemMessageContent(
  content: string,
  metadata: Record<string, unknown> | undefined,
  locale: Locale,
): string {
  if (isVisitorQueueEnteredContent(content)) {
    return t('chat.queue.entered', locale)
  }
  return resolveVisitorSystemEventContent(content, metadata, locale)
}

function QueueStatusNotice({
  locale,
  html,
  currentQueueCount,
}: {
  locale: Locale
  html: string
  currentQueueCount: number | null
}) {
  const showDefaultCopy = isDefaultQueueMessage(html)
  const renderedHtml = renderQueueMessage(showDefaultCopy ? DEFAULT_QUEUE_MESSAGE : html, currentQueueCount)
  const queueCountLabel = currentQueueCount == null
    ? t('chat.queue.waiting', locale)
    : t('chat.queue.waitingWithCount', locale, { count: currentQueueCount })

  return (
    <div className="px-5 py-1">
      <div className="flex items-start gap-3 border-l-2 border-primary/30 bg-primary/5 px-3 py-2">
        {showDefaultCopy ? (
          <div className="min-w-0 text-sm leading-6">
            <p className="font-medium text-foreground">
              {t('chat.queue.entered', locale)}
            </p>
            <p className="text-muted-foreground">{queueCountLabel}</p>
          </div>
        ) : (
          <SafeHtml
            className="prose prose-sm max-w-none text-sm leading-6 text-muted-foreground [&_p]:my-0"
            html={renderedHtml}
          />
        )}
      </div>
    </div>
  )
}

function UnreadReplyDivider({
  locale,
  unread,
  timestamp,
}: {
  locale: Locale
  unread: boolean
  timestamp?: string | null
}) {
  const timeLabel = timestamp ? formatMessageTime(new Date(timestamp), locale) : null
  return (
    <div className="px-5 py-2">
      <div className="flex items-center gap-3 text-xs text-muted-foreground">
        <div className="h-px flex-1 bg-border" />
        <div className="flex max-w-[80%] items-center gap-2">
          <span className="truncate">
            {t('chat.offlineReply.connected', locale)}
          </span>
          {unread && (
            <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-foreground">
              {t('chat.unread', locale)}
            </span>
          )}
          {timeLabel && <span className="hidden shrink-0 sm:inline">{timeLabel}</span>}
        </div>
        <div className="h-px flex-1 bg-border" />
      </div>
    </div>
  )
}

function isUnreadOfflineReply(
  conversation: VisitorConversationHistoryItem | VisitorUnreadOfflineReplyItem,
): conversation is VisitorUnreadOfflineReplyItem {
  return 'offline_message_public_id' in conversation
    && Boolean(conversation.offline_message_public_id)
}

function HistoryActionButton({
  label,
  loading,
  disabled,
  onClick,
}: {
  label: string
  loading?: boolean
  disabled?: boolean
  onClick?: () => void
}) {
  return (
    <button
      type="button"
      className="mx-auto my-2 flex items-center gap-1 rounded-full px-4 py-1.5 text-xs font-medium text-primary underline-offset-4 transition-colors hover:underline disabled:cursor-not-allowed disabled:text-muted-foreground disabled:no-underline"
      onClick={onClick}
      disabled={disabled || loading}
    >
      {loading && <IconLoader2 size={14} className="animate-spin" />}
      {label}
    </button>
  )
}

function VisitorWelcomeBubble({
  message,
  config,
  faq,
  faqDisabled,
  onFAQQuestionClick,
}: {
  message: Message
  config: ReturnType<typeof useVisitorChatConfig>['config']
  faq?: ReturnType<typeof getValidOpenAgentFAQ>
  faqDisabled?: boolean
  onFAQQuestionClick?: (text: string) => Promise<boolean> | boolean
}) {
  const openAgentWelcomeBlocks = getOpenAgentWelcomeBlocksFromMetadata(message.metadata)

  if (openAgentWelcomeBlocks.length > 0) {
    return (
      <>
        <OpenAgentWelcomeMessage
          blocks={openAgentWelcomeBlocks}
          config={config}
          showAvatar={shouldShowAssistantAvatar('bot', config)}
          avatarSrc={getOpenAgentAvatarUrl(config)}
        />
        {faq && (
          <div className="mt-2">
            <OpenAgentFAQMessage
              faq={faq}
              config={config}
              reserveAvatarSpace={shouldShowAssistantAvatar('bot', config)}
              faqDisabled={faqDisabled}
              onFAQQuestionClick={onFAQQuestionClick}
            />
          </div>
        )}
      </>
    )
  }

  return (
    <WelcomeMessage
      content={message.content}
      config={config}
      showAvatar={shouldShowAgentAvatar(null, config)}
      avatarSrc={getAgentAvatarUrl(null, config)}
    />
  )
}

function HistoryConversationBlock({
  conversation,
  config,
  locale,
}: {
  conversation: VisitorConversationHistoryItem | VisitorUnreadOfflineReplyItem
  config: ReturnType<typeof useVisitorChatConfig>['config']
  locale: Locale
}) {
  const startedAt = conversation.started_at || conversation.created_at || conversation.last_message_at
  const dividerLabel = startedAt
    ? `${formatMessageTime(new Date(startedAt), locale)} ${t('chat.history.pastConversation', locale)}`
    : t('chat.history.pastConversation', locale)
  const hasAgentUnread = (conversation.agent_unread_message_ids?.length ?? 0) > 0

  return (
    <div className="space-y-2">
      {isUnreadOfflineReply(conversation) ? (
        <UnreadReplyDivider
          locale={locale}
          unread={conversation.offline_reply_unread}
          timestamp={conversation.customer_unread_at || conversation.last_message_at}
        />
      ) : (
        <ConversationDivider
          label={dividerLabel}
          unreadLabel={
            hasAgentUnread ? t('chat.history.newReplies', locale) : null
          }
        />
      )}
      {conversation.messages_truncated && (
        <SystemMessage
          content={t('chat.history.latest200', locale)}
        />
      )}
      {conversation.messages.map((msg, idx) => {
        const prev = idx > 0 ? conversation.messages[idx - 1] : null
        const next = idx < conversation.messages.length - 1 ? conversation.messages[idx + 1] : null
        const showAvatar = msg.sender_type === 'agent' || msg.sender_type === 'bot'
          ? shouldShowAssistantAvatar(msg, config)
          : shouldShowAvatar(msg, next)

        if (msg.is_recalled && !shouldShowVisitorRecalledNotice(msg)) {
          return null
        }

        if (msg.sender_type === 'system') {
          return (
            <div
              key={msg.id}
              {...visitorMessageDomAttrs(msg)}
              className="rounded-2xl transition-colors duration-300"
            >
              {isOpenAgentHandoffEventMessage(msg) ? (
                <HumanHandoffEventMessage
                  content={msg.content}
                  config={config}
                  locale={locale}
                  handoffEventType={resolveHandoffEventType(msg.metadata)}
                />
              ) : isWelcomeLikeContentType(msg.content_type) || isLeaveMessagePromptMessage(msg) ? (
                <VisitorWelcomeBubble
                  message={msg}
                  config={config}
                />
              ) : (
                <SystemMessage content={displaySystemMessageContent(msg.content, msg.metadata, locale)} />
              )}
            </div>
          )
        }

        return (
          <div
            key={msg.id}
            {...visitorMessageDomAttrs(msg)}
            className="rounded-2xl transition-colors duration-300"
          >
            {shouldShowTimestamp(msg, prev) && (
              <div className="py-2 text-center text-[10px] text-muted-foreground">
                {formatMessageTime(new Date(msg.created_at), locale)}
              </div>
            )}
            <MessageBubble
              message={msg}
              config={config}
              showAvatar={showAvatar}
              showName={shouldShowName(msg, prev)}
              locale={locale}
              messageStatus={msg.status}
              showTime={false}
              allMessages={conversation.messages}
            />
          </div>
        )
      })}
    </div>
  )
}

// ─── Main Thread ────────────────────────────────────────────────

type VisitorThreadProps = {
  offlineTitle?: string
  offlineMessage?: string
  isEmbed?: boolean
  showHeader?: boolean
  onEmbedClose?: () => void
  composerFocusRequest?: number
  messageSoundEnabled?: boolean
  onMessageSoundEnabledChange?: (enabled: boolean) => void
}

export function VisitorThread({
  offlineTitle,
  offlineMessage,
  isEmbed = false,
  showHeader = true,
  onEmbedClose,
  composerFocusRequest = 0,
  messageSoundEnabled,
  onMessageSoundEnabledChange,
}: VisitorThreadProps) {
  const {
    channel,
    config,
    locale,
    isMobile,
    ended,
    conversationStatus,
    hasMore,
    loadingMore,
    historyAvailable,
    historyConversations,
    historyHasMore,
    historyLoading,
    historyLoaded,
    historyError,
    historyLimitReached,
    unreadReplyConversations,
    unreadReplyHasMore,
    unreadReplyError,
    currentUnreadReplyNotice,
    initializing,
    botMode,
    botRunning,
    offlineMode,
    queueFull,
    queueFullMessage,
    queueFullShowLeaveMessageButton,
    queueFullLeaveMessageButtonLabel,
    queueLeaveMessageLoading,
    handoffQueueFullInline,
    startConversationError,
    currentQueueCount,
    pendingHumanHandoff,
    satisfactionCanInitiate,
    satisfactionLoading,
    conversationPublicId,
    offlineMessagePublicId,
    visitorSessionToken,
    onLoadMore,
    onLoadHistory,
    onUnreadReplyVisible,
    onRestartConversation,
    onQueueFullLeaveMessage,
    onQueueLeaveMessage,
    onHandoffQueueFullContinueBot,
    onAssistSendMessage,
    onRetryOfflineMessage,
    onRetryOpenAgentAttachment,
    onRequestHumanHandoff,
    onDismissHumanHandoff,
    onSatisfactionInitiate,
    onSatisfactionSubmitted,
  } = useVisitorChatConfig()
  const agentTyping = useVisitorChatStore((s) => s.agentTyping)
  const msgCount = useVisitorChatStore((s) => s.messages.length)
  const messages = useVisitorChatStore((s) => s.messages)
  const dismissedHandoffToolCallIds = useVisitorChatStore((s) => s.dismissedHandoffToolCallIds)
  const confirmingHandoffToolCallIds = useVisitorChatStore((s) => s.confirmingHandoffToolCallIds)
  const confirmedHandoffToolCallIds = useMemo(
    () => collectConfirmedHandoffToolCallIds(messages),
    [messages],
  )
  const activeAgent = useVisitorChatStore((s) => s.activeAgent)
  const satisfactionInvitation = useVisitorChatStore((s) => s.satisfactionInvitation)
  const setSatisfactionInvitation = useVisitorChatStore((s) => s.setSatisfactionInvitation)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const pendingScrollDeltaRef = useRef<number | null>(null)
  const [surveyOpen, setSurveyOpen] = useState(false)
  const [surveyCollapsed, setSurveyCollapsed] = useState(false)
  const [surveySubmitting, setSurveySubmitting] = useState(false)
  const [surveySuccess, setSurveySuccess] = useState(false)
  const [surveyError, setSurveyError] = useState<string | null>(null)
  const [composerInsertRequest, setComposerInsertRequest] = useState<VisitorComposerInsertRequest | null>(null)
  const [suppressAnnouncementAutoPopup] = useState(isCurrentNavigationReload)
  const sendButtonStyle = {
    '--opendesk-send-button-bg': config.send_button_bg_color || 'var(--color-primary)',
  } as CSSProperties

  const initialPromptMessage = offlineMode
    ? config.leave_message_prompt
    : ''
  const openAgentWelcomeBlocks = useMemo(() => {
    const welcome = channel.open_agent_welcome_message
    if (!welcome?.enabled) return []
    return welcome.blocks.filter(isValidOpenAgentWelcomeBlock)
  }, [channel.open_agent_welcome_message])
  const openAgentFAQ = useMemo(
    () => getValidOpenAgentFAQ(channel.open_agent_welcome_message?.faq),
    [channel.open_agent_welcome_message?.faq],
  )
  const hasWelcomeMessage = messages.some((msg) => isWelcomeLikeContentType(msg.content_type))
  const hasLeaveMessagePromptMessage = messages.some((msg) => isLeaveMessagePromptMessage(msg))
  // Match the server-persisted prompt so the client preview and the server
  // message render identically. The offline message record (and its prompt
  // message) is only created on first send, so show the client preview until
  // then. offlineMessagePublicId stays null through the optimistic-send window,
  // so the preview no longer flashes out while the first message is in flight.
  const initialPromptPlainText = leaveMessagePromptToPlainText(initialPromptMessage)
  const showInitialPromptMessage = Boolean(initialPromptPlainText)
    && offlineMode
    && !offlineMessagePublicId
    && !hasLeaveMessagePromptMessage
    && !loadingMore
  const isOffline = Boolean(offlineMessage)
  const isQueued = conversationStatus === 'queued'
  const hasQueueEnteredMessage = useMemo(
    () => messages.some(isVisitorQueueEnteredMessage),
    [messages],
  )
  const conversationEnded = ended || conversationStatus === 'closed'
  const threadConversationStatus = conversationEnded ? 'closed' : conversationStatus
  const showQueueLeaveMessageButton = isQueued
    && !offlineMode
    && !conversationEnded
    && Boolean(conversationPublicId)
    && config.queue_show_leave_message_button
  const queueLeaveMessageButtonLabel = config.queue_leave_message_button_label
    || t('chat.leaveMessage.button', locale)
  const queueLeaveMessageButton = showQueueLeaveMessageButton ? (
    <div className="flex justify-center px-5 pb-1">
      <button
        type="button"
        data-action="queue-leave-message"
        onClick={() => void onQueueLeaveMessage()}
        disabled={queueLeaveMessageLoading}
        className="inline-flex min-h-7 items-center justify-center gap-1.5 rounded-md border border-[#D4D4D4] bg-white px-3 py-1 text-xs font-medium text-[#404040] transition-colors hover:bg-[#F5F5F5] disabled:pointer-events-none disabled:opacity-60"
      >
        {queueLeaveMessageLoading && <IconLoader2 size={13} className="animate-spin" />}
        {queueLeaveMessageButtonLabel}
      </button>
    </div>
  ) : null
  const showOpenAgentWelcomeMessage = !offlineMode
    && !conversationEnded
    && config.open_agent_enabled
    && openAgentWelcomeBlocks.length > 0
    && !hasWelcomeMessage
    && !loadingMore
  const showAnnouncement = Boolean(channel.announcement)
    && !initializing
  const oldestHistoryId = historyConversations[0]?.conversation_public_id
  const showCurrentDivider =
    unreadReplyConversations.length > 0
    || (historyLoaded && !isOffline && !offlineMode && historyConversations.length > 0)
  const showHistoryEntry = historyAvailable && !historyLoaded
  const showHistoryDone =
    historyLoaded && historyConversations.length > 0 && (!historyHasMore || historyLimitReached)
  const typingAgent = useMemo(() => {
    const latestAgentMessage = [...messages].reverse().find((msg) => msg.sender_type === 'agent')
    return {
      name: activeAgent?.name || latestAgentMessage?.sender_name || null,
      avatar: activeAgent?.avatar ?? latestAgentMessage?.sender_avatar ?? null,
    }
  }, [activeAgent, messages])
  const invitationLabel = useMemo(() => {
    const types = satisfactionInvitation?.survey_types ?? []
    if (types.includes('service') && types.includes('product')) {
      return t('chat.survey.invite.experience', locale)
    }
    if (types.includes('product')) {
      return t('chat.survey.invite.product', locale)
    }
    return t('chat.survey.invite.service', locale)
  }, [locale, satisfactionInvitation?.survey_types])
  const showFloatingInvitation =
    satisfactionInvitation && (ended || satisfactionInvitation.invitation_source !== 'visitor')
  const showComposerSatisfactionButton =
    !botMode && (satisfactionCanInitiate || satisfactionInvitation?.invitation_source === 'visitor')
  const currentUnreadReplyKey = currentUnreadReplyNotice?.conversationPublicId ?? null
  // Once a conversation appears in the loaded history (full transcript), drop it
  // from the proactive unread teasers so it is not duplicated and its full
  // context stays visible under "view history".
  const loadedHistoryIds = useMemo(
    () => new Set(historyConversations.map((conversation) => conversation.conversation_public_id)),
    [historyConversations],
  )
  const visibleUnreadReplyConversations = useMemo(
    () => unreadReplyConversations.filter(
      (conversation) => !loadedHistoryIds.has(conversation.conversation_public_id),
    ),
    [loadedHistoryIds, unreadReplyConversations],
  )
  const visibleUnreadReplyKey = useMemo(() => {
    const ids = unreadReplyConversations
      .filter((conversation) => conversation.offline_reply_unread)
      .map((conversation) => conversation.conversation_public_id)
    if (currentUnreadReplyNotice?.unread && currentUnreadReplyNotice.conversationPublicId) {
      ids.push(currentUnreadReplyNotice.conversationPublicId)
    }
    return Array.from(new Set(ids)).join('|')
  }, [currentUnreadReplyNotice, unreadReplyConversations])

  const handleComposerSatisfactionClick = useCallback(() => {
    if (satisfactionInvitation) {
      setSurveyOpen(true)
      return
    }

    void (async () => {
      try {
        const record = await onSatisfactionInitiate()
        if (record) setSurveyOpen(true)
      } catch {
        window.alert(t('chat.survey.openFailed', locale))
      }
    })()
  }, [locale, onSatisfactionInitiate, satisfactionInvitation])

  const requestComposerInsert = useCallback((request: Omit<VisitorComposerInsertRequest, 'id'>) => {
    setComposerInsertRequest((prev) => ({
      ...request,
      id: (prev?.id || 0) + 1,
    }))
  }, [])

  const handleSubmitSatisfaction = async (payload: SatisfactionSubmissionPayload) => {
    if (!conversationPublicId || !visitorSessionToken) return
    setSurveySubmitting(true)
    setSurveyError(null)
    try {
      await submitPublicSatisfaction({
        conversationPublicId,
        visitorSessionToken,
        payload,
      })
      setSurveySuccess(true)
      window.setTimeout(() => {
        setSurveyOpen(false)
        setSurveySuccess(false)
        setSatisfactionInvitation(null)
        onSatisfactionSubmitted()
      }, 1500)
    } catch {
      setSurveyError(t('chat.survey.submitFailed', locale))
    } finally {
      setSurveySubmitting(false)
    }
  }

  const loadHistoryWithAnchor = useCallback(
    async (beforeId?: string) => {
      const viewport = viewportRef.current
      pendingScrollDeltaRef.current = viewport ? viewport.scrollHeight - viewport.scrollTop : null
      await onLoadHistory(beforeId)
    },
    [onLoadHistory],
  )

  useLayoutEffect(() => {
    if (pendingScrollDeltaRef.current == null) return
    const viewport = viewportRef.current
    if (viewport) {
      viewport.scrollTop = viewport.scrollHeight - pendingScrollDeltaRef.current
    }
    pendingScrollDeltaRef.current = null
  }, [historyConversations.length])

  useLayoutEffect(() => {
    if (!currentUnreadReplyKey && unreadReplyConversations.length === 0) return
    const viewport = viewportRef.current
    if (!viewport) return
    viewport.scrollTop = 0
  }, [currentUnreadReplyKey, unreadReplyConversations.length])

  useEffect(() => {
    if (!visibleUnreadReplyKey) return
    if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
    visibleUnreadReplyKey.split('|').forEach((conversationPublicId) => {
      if (conversationPublicId) onUnreadReplyVisible(conversationPublicId)
    })
  }, [onUnreadReplyVisible, visibleUnreadReplyKey])

  return (
    <ThreadPrimitive.Root
      className="relative flex h-full flex-col"
      {...(threadConversationStatus ? { 'data-conversation-status': threadConversationStatus } : {})}
    >
      {showHeader && (
        <ChatHeader
          channel={channel}
          isMobile={isMobile}
          isEmbed={isEmbed}
          onEmbedClose={onEmbedClose}
          locale={locale}
          messageSoundEnabled={messageSoundEnabled}
          onMessageSoundEnabledChange={onMessageSoundEnabledChange}
        />
      )}

      <VisitorAnnouncement
        announcement={channel.announcement}
        visible={showAnnouncement}
        locale={locale}
        suppressAutoPopup={suppressAnnouncementAutoPopup}
      />

      <ThreadPrimitive.Viewport
        ref={viewportRef}
        className="relative flex flex-1 flex-col gap-2 overflow-y-auto py-3"
        style={{
          backgroundColor:
            config.message_area_bg_color || 'var(--color-background)',
        }}
      >
        {!initializing && unreadReplyError && (
          <SystemMessage
            content={t('chat.history.loadFailed', locale)}
          />
        )}

        {!initializing && unreadReplyHasMore && !historyLoaded && (
          <HistoryActionButton
            label={t('chat.history.moreReplies', locale)}
            loading={historyLoading}
            onClick={() => void loadHistoryWithAnchor()}
          />
        )}

        {!initializing && visibleUnreadReplyConversations.map((conversation) => (
          <HistoryConversationBlock
            key={`unread-${conversation.conversation_public_id}`}
            conversation={conversation}
            config={config}
            locale={locale}
          />
        ))}

        {!initializing && showHistoryEntry && !unreadReplyHasMore && (
          <HistoryActionButton
            label={
              historyError
                ? t('chat.history.retry', locale)
                : t('chat.history.view', locale)
            }
            loading={historyLoading}
            onClick={() => void loadHistoryWithAnchor()}
          />
        )}

        {!initializing && historyLoaded && historyHasMore && !historyLimitReached && (
          <HistoryActionButton
            label={
              historyError
                ? t('chat.history.retry', locale)
                : t('chat.history.loadMore', locale)
            }
            loading={historyLoading}
            onClick={() => void loadHistoryWithAnchor(oldestHistoryId)}
          />
        )}

        {!initializing && showHistoryDone && (
          <HistoryActionButton
            label={
              historyLimitReached
                ? t('chat.history.limitReached', locale)
                : t('chat.history.noMore', locale)
            }
            disabled
          />
        )}

        {!initializing && historyConversations.map((conversation) => (
          <HistoryConversationBlock
            key={conversation.conversation_public_id}
            conversation={conversation}
            config={config}
            locale={locale}
          />
        ))}

        {!initializing && showCurrentDivider && (
          <ConversationDivider label={t('chat.history.current', locale)} />
        )}

        {initializing ? (
          <div className="flex flex-1 items-center justify-center p-6">
            <IconLoader2 size={28} className="animate-spin text-muted-foreground" />
          </div>
        ) : startConversationError ? (
          <div className="flex flex-1 items-center justify-center p-6">
            <div className="w-full max-w-[520px] rounded-xl border border-destructive/20 bg-destructive/5 p-6 shadow-sm">
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-destructive">
                <IconAlertCircle size={18} />
                {t('chat.start.noAssignableQueueTitle', locale)}
              </div>
              <p className="text-sm leading-6 text-muted-foreground">{startConversationError}</p>
            </div>
          </div>
        ) : isOffline ? (
          <div className="flex flex-1 items-center justify-center p-6">
            <div className="w-full max-w-[520px] rounded-xl border border-border bg-card p-6 shadow-sm">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                <IconAlertCircle size={18} className="text-amber-600" />
                {offlineTitle || t('chat.offline.title', locale)}
              </div>
              <SafeHtml
                className="prose prose-sm max-w-none text-sm leading-6 text-muted-foreground"
                html={offlineMessage || ''}
              />
            </div>
          </div>
        ) : queueFull ? (
          <div className="flex flex-1 items-center justify-center p-6">
            <div className="w-full max-w-[520px] rounded-xl border border-border bg-card p-6 shadow-sm">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                <IconAlertCircle size={18} className="text-amber-600" />
                {t('chat.queue.full', locale)}
              </div>
              <SafeHtml
                className="prose prose-sm max-w-none text-sm leading-6 text-muted-foreground"
                html={queueFullMessage}
              />
              {queueFullShowLeaveMessageButton && (
                <button
                  type="button"
                  onClick={onQueueFullLeaveMessage}
                  className="mt-5 rounded-lg bg-[var(--opendesk-send-button-bg)] px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
                  style={sendButtonStyle}
                >
                  {queueFullLeaveMessageButtonLabel || t('chat.leaveMessage.button', locale)}
                </button>
              )}
            </div>
          </div>
        ) : (
          <>
            {isQueued && !hasQueueEnteredMessage && (
              <>
                <QueueStatusNotice
                  locale={locale}
                  html={config.queue_message}
                  currentQueueCount={currentQueueCount}
                />
                {queueLeaveMessageButton}
              </>
            )}

            {/* ── Initial leave-message prompt ── */}
            {showInitialPromptMessage && (
              <div className="py-2">
                <WelcomeMessage
                  content={initialPromptPlainText}
                  config={config}
                  showAvatar={shouldShowAgentAvatar(null, config)}
                  avatarSrc={getAgentAvatarUrl(null, config)}
                />
              </div>
            )}

            {currentUnreadReplyNotice && (
              <UnreadReplyDivider
                locale={locale}
                unread={currentUnreadReplyNotice.unread}
              />
            )}

            {/* ── Load more ── */}
            {msgCount > 0 && hasMore && (
              <button
                className="mx-auto mb-2 flex items-center gap-1 rounded-full px-4 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted"
                onClick={onLoadMore}
                disabled={loadingMore}
              >
                {loadingMore ? (
                  <IconLoader2 size={14} className="animate-spin" />
                ) : (
                  t('chat.loadMore', locale)
                )}
              </button>
            )}

            {showOpenAgentWelcomeMessage && (
              <div className={msgCount === 0 ? 'py-2' : 'py-1'}>
                <OpenAgentWelcomeMessage
                  blocks={openAgentWelcomeBlocks}
                  config={config}
                  showAvatar={shouldShowAssistantAvatar('bot', config)}
                  avatarSrc={getOpenAgentAvatarUrl(config)}
                />
                {openAgentFAQ && (
                  <div className="mt-2">
                    <OpenAgentFAQMessage
                      faq={openAgentFAQ}
                      config={config}
                      reserveAvatarSpace={shouldShowAssistantAvatar('bot', config)}
                      faqDisabled={botRunning || !conversationPublicId}
                      onFAQQuestionClick={onAssistSendMessage}
                    />
                  </div>
                )}
              </div>
            )}

            {/* ── Messages (via assistant-ui) ── */}
            {msgCount > 0 && (
              <ThreadPrimitive.Messages>
                {({ message }: { message: MessageState }) => {
                  const meta = message.metadata?.custom as VisitorMessageMeta | undefined
                  const original = toOriginalMessage(message, meta)
                  const isWelcomeMessage = isWelcomeLikeContentType(original.content_type)
                  const isWelcomeLikeMessage = isWelcomeMessage || isLeaveMessagePromptMessage(original)
                  const isQueueEnteredSystemMessage =
                    message.role === 'system' && isVisitorQueueEnteredContent(original.content)
                  const shouldHideEndedWelcomeMessage = conversationEnded && isWelcomeMessage
                  const shouldHideAgentRecalledMessage =
                    original.is_recalled && !shouldShowVisitorRecalledNotice(original)

                  if (shouldHideAgentRecalledMessage) return null

                  return (
                    <div
                      {...visitorMessageDomAttrs(original, { messageStatus: meta?.messageStatus })}
                      className="rounded-2xl transition-colors duration-300"
                    >
                      {meta?.showTimestamp && message.createdAt && (
                        <div className="py-2 text-center text-[10px] text-muted-foreground">
                          {formatMessageTime(message.createdAt, locale)}
                        </div>
                      )}

                      {shouldHideEndedWelcomeMessage ? null : isWelcomeLikeMessage ? (
                        <VisitorWelcomeBubble
                          message={original}
                          config={config}
                          faq={openAgentFAQ}
                          faqDisabled={botRunning || !conversationPublicId}
                          onFAQQuestionClick={onAssistSendMessage}
                        />
                      ) : message.role === 'system' ? (
                        isOpenAgentHandoffEventMessage(original) ? (
                          (() => {
                            const confirmCardState = resolveHandoffConfirmCardState(
                              original,
                              pendingHumanHandoff,
                              dismissedHandoffToolCallIds,
                              confirmingHandoffToolCallIds,
                              confirmedHandoffToolCallIds,
                            )
                            return (
                              <HumanHandoffEventMessage
                                content={original.content}
                                config={config}
                                locale={locale}
                                handoffEventType={resolveHandoffEventType(original.metadata)}
                                confirmCardState={confirmCardState}
                                onConfirmHandoff={
                                  confirmCardState === 'active' && pendingHumanHandoff
                                    ? () => void onRequestHumanHandoff(pendingHumanHandoff.payload)
                                    : undefined
                                }
                                onDismissHandoff={
                                  confirmCardState === 'active'
                                    ? onDismissHumanHandoff
                                    : undefined
                                }
                              />
                            )
                          })()
                        ) : (
                          <>
                            <SystemMessage content={displaySystemMessageContent(original.content, original.metadata, locale)} />
                            {isQueued && isQueueEnteredSystemMessage && (
                              <>
                                <QueueStatusNotice
                                  locale={locale}
                                  html={config.queue_message}
                                  currentQueueCount={currentQueueCount}
                                />
                                {queueLeaveMessageButton}
                              </>
                            )}
                          </>
                        )
                      ) : (
                        <MessageBubble
                          message={original}
                          config={config}
                          showAvatar={meta?.showAvatar ?? true}
                          showName={meta?.showName ?? true}
                          locale={locale}
                          messageStatus={meta?.messageStatus}
                          showTime={false}
                          renderAssistantParts
                          allMessages={messages}
                          onEditRecalledMessage={requestComposerInsert}
                          onRetryMessage={
                            offlineMode && original.status === 'failed'
                              ? (failedMessage) => void onRetryOfflineMessage(failedMessage)
                              : botMode
                                && original.status === 'failed'
                                && original.metadata?.open_agent_attachment === true
                                ? (failedMessage) => void onRetryOpenAgentAttachment(failedMessage)
                              : undefined
                          }
                        />
                      )}
                    </div>
                  )
                }}
              </ThreadPrimitive.Messages>
            )}

            {/* ── Bot handoff queue-full card (leave message / keep chatting) ── */}
            {handoffQueueFullInline && (
              <HandoffQueueFullCard
                locale={locale}
                message={queueFullMessage}
                showLeaveMessageButton={queueFullShowLeaveMessageButton}
                leaveMessageButtonLabel={queueFullLeaveMessageButtonLabel}
                sendButtonBgColor={config.send_button_bg_color}
                onLeaveMessage={onQueueFullLeaveMessage}
                onContinueBot={onHandoffQueueFullContinueBot}
              />
            )}

            {/* ── Typing indicator ── */}
            {agentTyping && !botMode && !offlineMode && (
              <TypingIndicator
                agentBubbleBg={config.agent_bubble_bg_color || undefined}
                agentBubbleTextColor={config.agent_bubble_text_color || undefined}
                agentBubbleRadius={config.agent_bubble_radius}
                agentBubbleBorder={config.agent_bubble_border_color || undefined}
                showAvatar={shouldShowAgentAvatar(typingAgent.avatar, config)}
                agentAvatar={getAgentAvatarUrl(typingAgent.avatar, config)}
                agentName={typingAgent.name}
                locale={locale}
              />
            )}

            {/* ── Scroll-to-bottom (sticky; mt-auto keeps it at message-area bottom when history is short) ── */}
            <ThreadPrimitive.ViewportFooter className="sticky bottom-0 mt-auto">
              <div className="flex justify-center pb-2">
                <ThreadPrimitive.ScrollToBottom className="flex h-8 w-8 cursor-pointer items-center justify-center rounded-full border border-border bg-background text-muted-foreground shadow-md transition-colors hover:bg-muted disabled:pointer-events-none disabled:hidden">
                  <IconArrowDown size={16} />
                </ThreadPrimitive.ScrollToBottom>
              </div>
            </ThreadPrimitive.ViewportFooter>
          </>
        )}
      </ThreadPrimitive.Viewport>

      {!initializing && !isOffline && showFloatingInvitation && (
        <div className="pointer-events-none absolute inset-x-0 bottom-[88px] z-30 flex justify-center px-4">
          <div
            className="pointer-events-auto flex items-center gap-2 rounded-full bg-[var(--opendesk-send-button-bg)] px-3 py-2 text-sm font-medium text-primary-foreground shadow-lg"
            style={sendButtonStyle}
          >
            <button
              type="button"
              onClick={() => setSurveyOpen(true)}
              className="flex min-h-5 items-center gap-2"
            >
              <IconStar size={14} className="fill-current" aria-hidden />
              <span>{surveyCollapsed ? t('chat.survey.rate', locale) : invitationLabel}</span>
            </button>
            {!surveyCollapsed && (
              <button
                type="button"
                onClick={() => setSurveyCollapsed(true)}
                className="flex h-5 w-5 items-center justify-center rounded-full text-primary-foreground/80 hover:bg-primary-foreground/10 hover:text-primary-foreground"
                aria-label={t('chat.survey.collapse', locale)}
              >
                <IconX size={13} aria-hidden />
              </button>
            )}
          </div>
        </div>
      )}

      {!initializing && !isOffline && surveyOpen && satisfactionInvitation && (
        <SatisfactionSurveyModal
          record={satisfactionInvitation}
          locale={locale}
          submitting={surveySubmitting}
          success={surveySuccess}
          error={surveyError}
          sendButtonBgColor={config.send_button_bg_color}
          onSubmit={handleSubmitSatisfaction}
          onClose={() => setSurveyOpen(false)}
        />
      )}

      {!initializing && !isOffline && !queueFull && (
        ended ? (
          <ConversationEndedPanel
            locale={locale}
            sendButtonBgColor={config.send_button_bg_color}
            onRestartConversation={onRestartConversation}
          />
        ) : (
          <VisitorComposer
            disabled={false}
            isMobile={isMobile}
            isEmbed={isEmbed}
            focusRequest={composerFocusRequest}
            insertRequest={composerInsertRequest}
            showSatisfactionButton={showComposerSatisfactionButton}
            satisfactionLoading={satisfactionLoading}
            onSatisfactionClick={handleComposerSatisfactionClick}
          />
        )
      )}
    </ThreadPrimitive.Root>
  )
}

function ConversationEndedPanel({
  locale,
  sendButtonBgColor,
  onRestartConversation,
}: {
  locale: Locale
  sendButtonBgColor: string | null
  onRestartConversation: () => Promise<void>
}) {
  const [restarting, setRestarting] = useState(false)
  const restartButtonStyle = {
    backgroundColor: sendButtonBgColor || 'var(--color-primary)',
  } as CSSProperties

  const handleRestart = async () => {
    setRestarting(true)
    try {
      await onRestartConversation()
    } finally {
      setRestarting(false)
    }
  }

  return (
    <div className="shrink-0 bg-background px-3 py-2 sm:px-4 sm:py-3">
      <div className="flex min-h-[92px] items-center justify-between gap-3 rounded-[14px] border border-border bg-background px-4 py-3 sm:rounded-2xl">
        <span className="text-sm text-muted-foreground">
          {t('chat.ended', locale)}
        </span>
        <button
          type="button"
          onClick={handleRestart}
          disabled={restarting}
          className="shrink-0 rounded-full px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          style={restartButtonStyle}
        >
          {restarting
            ? t('chat.restarting', locale)
            : t('chat.restart', locale)}
        </button>
      </div>
    </div>
  )
}
