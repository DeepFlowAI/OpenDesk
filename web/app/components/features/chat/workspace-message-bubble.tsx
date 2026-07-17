'use client'

import { useCallback, useEffect, useRef, useState, type MouseEvent as ReactMouseEvent, type ReactNode } from 'react'
import type { Locale } from '@/context/locale-store'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import { getBoundedFixedMenuPosition } from '@/lib/floating-menu-position'
import { getSelectionTextWithin } from '@/lib/clipboard'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { resolveOpenAgentHandoffEventLabel } from '@/lib/open-agent-handoff-event'
import { isLeaveMessagePromptMessage } from '@/lib/offline-message-event'
import { isBotWelcomeContentType, isWelcomeLikeContentType } from '@/lib/welcome-message-content-type'
import { getOpenAgentWelcomeBlocksFromMetadata } from '@/lib/open-agent-welcome-message'
import { messageQuoteFromMetadata } from '@/lib/message-quote'
import {
  getWorkspaceAgentAvatarLetter,
  getWorkspaceHumanAgentLabel,
  sanitizeWorkspaceAgentEventContent,
  resolveWorkspaceSystemEventContent,
} from '@/lib/workspace-agent-display'
import { MarkdownText, markdownTextRootClass } from '@/components/assistant-ui/markdown-text'
import { SafeHtml } from '@/components/safe-html'
import { LinkifiedText } from '@/app/components/features/chat/linkified-text'
import {
  MessageStatusIcon,
  resolveVisibleMessageStatus,
} from '@/app/components/features/chat/message-status-icon'
import { MessageAttachment, type MessageAttachmentGalleryItem } from '@/app/components/features/chat/message-attachment'
import { MessageQuoteBlock } from '@/app/components/features/chat/message-quote'
import { OpenAgentFeedbackStatus } from '@/app/components/features/chat/open-agent-feedback'
import { RichTextMessageContent } from '@/app/components/features/chat/rich-text-message-content'
import {
  OpenAgentTextBlockView,
  OpenAgentTraceBlocks,
  getOpenAgentTextBlocks,
  getOpenAgentThinkingBlocks,
  getVisibleOpenAgentToolBlocks,
  stripOpenAgentThinkSections,
} from '@/app/components/features/chat/open-agent-trace-blocks'
import { OpenAgentWelcomeMessage } from '@/app/components/features/visitor-chat/welcome-message'
import type { Message } from '@/models/conversation'
import type { SessionRecordMessage } from '@/models/session-record'

// ─── Types ───────────────────────────────────────────────────────

export type WorkspaceMessageBubbleMode = 'active' | 'preview' | 'record'

export type WorkspaceMessageAttachmentContext =
  | { kind: 'conversation'; conversationId: number; conversationPublicId?: string | null }
  | { kind: 'offline_message'; offlineMessageId: number }

export type WorkspaceMessageBubbleProps = {
  message: Message
  locale: Locale
  mode: WorkspaceMessageBubbleMode
  attachmentContext: WorkspaceMessageAttachmentContext
  visitorName?: string | null
  visitorAvatarColor?: string | null
  imageGallery?: MessageAttachmentGalleryItem[]
  allMessages?: Message[]
  currentUserId?: number | null
  readStatusEnabled?: boolean
  inlinePlayableVideo?: boolean
  muted?: boolean
  showTimestamp?: boolean
  /** Show the human agent's name label. Defaults to true. Active/history views
   *  in the current conversation suppress it. */
  showAgentName?: boolean
  /** Show the visitor's name label. Defaults to true. Active/history views
   *  in the current conversation suppress it. */
  showVisitorName?: boolean
  /** Keep the visitor avatar visible. The active chat workspace disables it. */
  showVisitorAvatar?: boolean
  /** Keep agent, bot, and welcome-message avatars visible. */
  showAssistantAvatar?: boolean
  onSatisfactionEventClick?: () => void
  onLocateQuotedMessage?: (messageId: number) => void
  // Active-mode interactions. Each action is only offered when its callback is
  // provided; the caller decides whether the action is currently permitted.
  onCopyMessage?: (message: Message, selectedText?: string) => void
  onAddKnowledgeInspiration?: (message: Message) => void
  onCreateKnowledgeDocument?: (message: Message) => void
  onCreateRobotQa?: (message: Message) => void
  onQuoteMessage?: (message: Message) => void
  onRecallMessage?: (message: Message) => void
  onEditRecalledMessage?: (message: Message) => void
  onRetryMessage?: (message: Message) => void
}

const MESSAGE_ACTION_MENU_WIDTH = 152
const MESSAGE_ACTION_MENU_VERTICAL_PADDING = 8
const MESSAGE_ACTION_MENU_ITEM_HEIGHT = 32

// ─── Adapters ────────────────────────────────────────────────────

/**
 * Session record messages are structurally almost identical to project
 * messages. Map them so the shared bubble can consume a single input type.
 * `satisfaction_record_id` is preserved for satisfaction event handling.
 */
export function sessionRecordMessageToMessage(record: SessionRecordMessage): Message {
  return {
    id: record.id,
    conversation_id: record.conversation_id,
    sender_type: record.sender_type,
    sender_id: record.sender_id,
    sender_name: record.sender_name,
    sender_avatar: record.sender_avatar,
    content_type: record.content_type,
    content: record.content,
    is_recalled: record.is_recalled,
    recalled_at: record.recalled_at,
    recalled_by_type: record.recalled_by_type,
    recalled_by_id: record.recalled_by_id,
    recalled_by_name: record.recalled_by_name,
    metadata: record.metadata,
    created_at: record.created_at,
    event_type: record.event_type as Message['event_type'],
    satisfaction_record_id: record.satisfaction_record_id,
    config_version: record.config_version,
  }
}

// ─── Time helpers ────────────────────────────────────────────────

function formatShortTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function formatFullTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d
    .toLocaleString('sv-SE', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    })
    .replace('T', ' ')
}

// ─── Read status ─────────────────────────────────────────────────

function isReadStatusContentType(contentType: string | undefined): boolean {
  return (
    contentType === 'text' || contentType === 'rich_text' || contentType === 'image' || contentType === 'file'
  )
}

function recalledMessageText(input: {
  locale: Locale
  isOwn?: boolean
  senderType?: string
  senderName?: string | null
}): string {
  const { locale, isOwn, senderType, senderName } = input
  if (isOwn) return t('ws.chat.recall.youRecalled', locale)
  if (senderType === 'visitor') return t('ws.chat.recall.visitorRecalled', locale)
  if (senderName) return t('ws.chat.recall.namedRecalled', locale, { name: senderName })
  return t('ws.chat.recall.otherRecalled', locale)
}

// ─── Presentational sub-components ───────────────────────────────

const internalNoteBubbleClass = 'border border-[#F4C35E] bg-[#FFE6A6]'

function AgentAvatar({
  avatar,
  name,
  isBot,
  muted = false,
}: {
  avatar?: string | null
  name?: string | null
  isBot: boolean
  muted?: boolean
}) {
  const label = getWorkspaceAgentAvatarLetter(isBot, name)
  return (
    <div
      className={cn(
        'flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full text-sm font-medium',
        muted ? 'bg-[#E8E8E8] text-[#737373]' : 'bg-[#D6E6F9] text-[#4A80B5]',
      )}
    >
      {avatar ? <img src={avatar} alt={name || label} className="h-full w-full object-cover" /> : label}
    </div>
  )
}

function VisitorAvatar({ char, color }: { char: string; color: string }) {
  return (
    <div
      data-testid="visitor-message-avatar"
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white"
      style={{ backgroundColor: color }}
    >
      {char}
    </div>
  )
}

function SystemAgentAvatar({ muted = false }: { muted?: boolean }) {
  return (
    <div
      className={cn(
        'flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium',
        muted ? 'bg-[#E8E8E8] text-[#737373]' : 'bg-[#D6E6F9] text-[#4A80B5]',
      )}
    >
      s
    </div>
  )
}

function AgentSideWelcomeBubble({
  content,
  time,
  muted = false,
  avatar,
  showAvatar = true,
}: {
  content: string
  time: string
  muted?: boolean
  avatar?: ReactNode
  showAvatar?: boolean
}) {
  return (
    <div className="mb-4 flex flex-row-reverse gap-2.5">
      {showAvatar && (avatar ?? <SystemAgentAvatar muted={muted} />)}
      <div className="flex min-w-0 max-w-[70%] flex-col items-end">
        {time && <span className="mb-1 text-right text-[11px] text-[#999999]">{time}</span>}
        <SafeHtml
          html={content}
          className={cn(
            'max-w-full rounded-[12px] px-3.5 py-2.5 text-sm leading-normal break-words break-all whitespace-pre-wrap text-[#1a1a1a]',
            muted ? 'bg-[#E8E8E8]' : 'bg-[#DBEAFE]',
            richTextListStyleClass,
          )}
        />
      </div>
    </div>
  )
}

function RecalledMessageNotice({
  text,
  time,
  alignEnd,
  editLabel,
  onEdit,
}: {
  text: string
  time?: string
  alignEnd?: boolean
  editLabel?: string
  onEdit?: () => void
}) {
  return (
    <div className={cn('flex min-w-0 flex-col', alignEnd ? 'items-end' : 'items-start')}>
      <div className="max-w-full rounded-[12px] border border-dashed border-[#D8D8D8] bg-[#F5F5F5] px-3.5 py-2 text-sm leading-normal text-[#737373]">
        <span>{text}</span>
        {onEdit && editLabel && (
          <button
            type="button"
            className="ml-2 text-primary underline-offset-2 hover:underline"
            onClick={onEdit}
          >
            {editLabel}
          </button>
        )}
      </div>
      {time && <span className="mt-1 text-[11px] text-[#999999]">{time}</span>}
    </div>
  )
}

// ─── Shared bubble ───────────────────────────────────────────────

export function WorkspaceMessageBubble({
  message,
  locale,
  mode,
  attachmentContext,
  visitorName,
  visitorAvatarColor,
  imageGallery,
  allMessages,
  currentUserId,
  readStatusEnabled = false,
  inlinePlayableVideo = false,
  muted,
  showTimestamp,
  showAgentName = true,
  showVisitorName = true,
  showVisitorAvatar = true,
  showAssistantAvatar = true,
  onSatisfactionEventClick,
  onLocateQuotedMessage,
  onCopyMessage,
  onAddKnowledgeInspiration,
  onCreateKnowledgeDocument,
  onCreateRobotQa,
  onQuoteMessage,
  onRecallMessage,
  onEditRecalledMessage,
  onRetryMessage,
}: WorkspaceMessageBubbleProps) {
  const isMuted = muted ?? mode === 'record'
  const displayTimestamp = showTimestamp ?? mode !== 'preview'

  const [messageMenu, setMessageMenu] = useState<{ x: number; y: number } | null>(null)
  // Captures the highlighted text at right-click time, since clicking a menu
  // item clears the browser selection before we can read it.
  const selectedTextRef = useRef<string>('')

  useEffect(() => {
    if (!messageMenu) return
    const close = () => setMessageMenu(null)
    window.addEventListener('click', close)
    window.addEventListener('scroll', close, true)
    window.addEventListener('keydown', close)
    return () => {
      window.removeEventListener('click', close)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('keydown', close)
    }
  }, [messageMenu])

  const canCopy = Boolean(onCopyMessage)
  const canAddKnowledgeInspiration = Boolean(onAddKnowledgeInspiration)
  const canCreateKnowledgeDocument = Boolean(onCreateKnowledgeDocument)
  const canCreateRobotQa = Boolean(onCreateRobotQa)
  const canQuote = Boolean(onQuoteMessage)
  const canRecall = Boolean(onRecallMessage)
  const hasMenuActions = canCopy || canAddKnowledgeInspiration || canCreateKnowledgeDocument || canCreateRobotQa || canQuote || canRecall

  const handleContextMenu = useCallback(
    (event: ReactMouseEvent<HTMLDivElement>) => {
      if (!hasMenuActions) return
      event.preventDefault()
      selectedTextRef.current = getSelectionTextWithin(event.currentTarget)
      const itemCount = Number(canCopy)
        + Number(canAddKnowledgeInspiration)
        + Number(canCreateKnowledgeDocument)
        + Number(canCreateRobotQa)
        + Number(canQuote)
        + Number(canRecall)
      setMessageMenu(
        getBoundedFixedMenuPosition(
          { x: event.clientX, y: event.clientY },
          {
            width: MESSAGE_ACTION_MENU_WIDTH,
            height: MESSAGE_ACTION_MENU_VERTICAL_PADDING + MESSAGE_ACTION_MENU_ITEM_HEIGHT * itemCount,
          },
        ),
      )
    },
    [canAddKnowledgeInspiration, canCopy, canCreateKnowledgeDocument, canCreateRobotQa, canQuote, canRecall, hasMenuActions],
  )

  const isAgent = message.sender_type === 'agent'
  const isBot = message.sender_type === 'bot'
  const isAssistantSide = isAgent || isBot
  const isSystem = message.sender_type === 'system'
  const isInternalNote = message.content_type === 'internal_note'

  const visitorColor = visitorAvatarColor || '#4A8C5C'
  const visitorChar = (visitorName || message.sender_name || '访').charAt(0)

  const attachmentContentType =
    message.content_type === 'image' ? 'image' : message.content_type === 'file' ? 'file' : null
  const isRichText = message.content_type === 'rich_text'
  const textBlocks = isBot ? getOpenAgentTextBlocks(message.metadata) : []
  const thinkingBlocks = isBot ? getOpenAgentThinkingBlocks(message.metadata) : []
  const visibleToolBlocks = isBot ? getVisibleOpenAgentToolBlocks(message.metadata) : []
  const hasOpenAgentTrace =
    isBot && (textBlocks.length > 0 || thinkingBlocks.length > 0 || visibleToolBlocks.length > 0)
  const hasMessageText = message.content.trim().length > 0

  const shortTime = formatShortTime(message.created_at)
  const fullTimeTitle = mode === 'record' ? formatFullTime(message.created_at) : undefined

  // 1. Recalled
  if (message.is_recalled) {
    return (
      <div className={cn('mb-4 flex gap-2.5', isMuted && 'opacity-90', isAssistantSide ? 'flex-row-reverse' : 'flex-row')}>
        {isAssistantSide ? (
          showAssistantAvatar
            ? <AgentAvatar avatar={message.sender_avatar} name={message.sender_name} isBot={isBot} muted={isMuted} />
            : null
        ) : message.sender_type !== 'visitor' || showVisitorAvatar ? (
          <VisitorAvatar char={visitorChar} color={visitorColor} />
        ) : null}
        <RecalledMessageNotice
          text={recalledMessageText({
            locale,
            isOwn: isAgent && message.sender_id === currentUserId,
            senderType: message.sender_type,
            senderName: message.sender_name,
          })}
          time={shortTime}
          alignEnd={isAssistantSide}
          editLabel={onEditRecalledMessage ? t('ws.chat.recall.editAgain', locale) : undefined}
          onEdit={onEditRecalledMessage ? () => onEditRecalledMessage(message) : undefined}
        />
      </div>
    )
  }

  // 2. Welcome / bot welcome / leave-message prompt
  const isWelcomeLike = isWelcomeLikeContentType(message.content_type)
  const isLeavePrompt = isSystem && !isInternalNote && isLeaveMessagePromptMessage(message)
  if (isWelcomeLike || isLeavePrompt) {
    // Bot welcome messages reuse the same placeholder avatar (bot name initial)
    // as regular bot messages; other welcome/leave prompts keep the system avatar.
    const isBotWelcome = isBotWelcomeContentType(message.content_type)
    const botWelcomeName =
      (typeof message.metadata?.open_agent_agent_name === 'string'
        ? message.metadata.open_agent_agent_name.trim()
        : '') || message.sender_name
    const welcomeAvatar = isBotWelcome ? (
      <AgentAvatar avatar={message.sender_avatar} name={botWelcomeName} isBot muted={isMuted} />
    ) : (
      <SystemAgentAvatar muted={isMuted} />
    )
    const welcomeBlocks = getOpenAgentWelcomeBlocksFromMetadata(message.metadata)
    if (welcomeBlocks.length > 0) {
      return (
        <div className="mb-4">
          <OpenAgentWelcomeMessage
            blocks={welcomeBlocks}
            align="end"
            avatarNode={showAssistantAvatar ? welcomeAvatar : undefined}
          />
        </div>
      )
    }
    return (
      <AgentSideWelcomeBubble
        content={message.content}
        time={shortTime}
        muted={isMuted}
        avatar={welcomeAvatar}
        showAvatar={showAssistantAvatar}
      />
    )
  }

  // 3. Satisfaction event
  if (message.content_type === 'satisfaction_event') {
    const submitted = message.event_type === 'feedback_submitted'
    return (
      <div className="mb-4 flex flex-col items-center py-1">
        <button
          type="button"
          onClick={onSatisfactionEventClick}
          disabled={!onSatisfactionEventClick}
          className={cn(
            'rounded-full px-3 py-1.5 text-center text-[12px] font-medium leading-normal transition-opacity',
            onSatisfactionEventClick && 'hover:opacity-80',
            submitted ? 'bg-[#F0FDF4] text-[#16A34A]' : 'bg-[#EFF6FF] text-[#3B82F6]',
          )}
        >
          {sanitizeWorkspaceAgentEventContent(message.content, locale)}
        </button>
        {displayTimestamp && (
          <span className="mt-0.5 text-[10px] text-muted-foreground" title={fullTimeTitle}>
            {shortTime}
          </span>
        )}
      </div>
    )
  }

  // 4. System event
  if (isSystem && !isInternalNote) {
    const handoffEventLabel = resolveOpenAgentHandoffEventLabel(message.metadata, locale)
    const systemContent = handoffEventLabel || message.content
    return (
      <div className="mb-4 flex flex-col items-center py-1">
        <span className="text-center text-[12px] leading-normal text-[#999999]">
          {resolveWorkspaceSystemEventContent(systemContent, message.metadata, locale)}
        </span>
        {displayTimestamp && (
          <span className="mt-0.5 text-[10px] text-muted-foreground" title={fullTimeTitle}>
            {shortTime}
          </span>
        )}
      </div>
    )
  }

  // 5. Empty bot message
  if (isBot && !attachmentContentType && !hasOpenAgentTrace && !hasMessageText) return null

  // Quote block
  const quote = messageQuoteFromMetadata(message.metadata)
  const quotedOriginal =
    quote && allMessages ? allMessages.find((item) => item.id === quote.message_id) ?? null : null
  const quoteAttachmentContext =
    attachmentContext.kind === 'conversation'
      ? {
          conversationId: attachmentContext.conversationId,
          conversationPublicId: attachmentContext.conversationPublicId ?? undefined,
        }
      : undefined
  const handleQuoteClick =
    quote && onLocateQuotedMessage ? () => onLocateQuotedMessage(quote.message_id) : undefined
  const quoteBlock = quote ? (
    <MessageQuoteBlock
      quote={quote}
      locale={locale}
      original={quotedOriginal}
      onClick={handleQuoteClick}
      attachmentContext={quoteAttachmentContext}
      className="max-w-full rounded-lg"
    />
  ) : null
  const embeddedQuoteBlock = quote ? (
    <MessageQuoteBlock
      quote={quote}
      locale={locale}
      original={quotedOriginal}
      onClick={handleQuoteClick}
      variant="embedded"
      attachmentContext={quoteAttachmentContext}
      className="mb-2"
    />
  ) : null

  // Bubble styling
  const bubbleClassName = cn(
    'max-w-full rounded-[12px] px-3.5 py-2.5 text-sm leading-normal break-words break-all text-[#1a1a1a]',
    isInternalNote
      ? internalNoteBubbleClass
      : isAssistantSide
        ? isMuted
          ? 'bg-[#E8E8E8]'
          : 'bg-[#DBEAFE]'
        : isMuted
          ? 'border border-[#E0E0E0] bg-white'
          : 'border border-[#E0E0E0] bg-[#F0F0F0]',
  )

  // Sender label
  const senderLabel = isAssistantSide
    ? isBot
      ? message.sender_name || (locale === 'zh' ? '智能助手' : 'Assistant')
      : showAgentName
        ? message.sender_name || getWorkspaceHumanAgentLabel(locale)
        : null
    : showVisitorName
      ? visitorName || message.sender_name || t('ws.chat.queueVisitor', locale)
      : null

  const isOwnStatusMessage =
    isAgent
    && message.sender_id === currentUserId
    && isReadStatusContentType(message.content_type)
  const visibleStatus = isOwnStatusMessage
    ? resolveVisibleMessageStatus(message.status, { enabled: readStatusEnabled })
    : null
  const failedStatusText = isOwnStatusMessage && message.status === 'failed'
    ? t('ws.chat.messageStatus.failed', locale)
    : null

  const conversationAttachmentId =
    attachmentContext.kind === 'conversation' ? attachmentContext.conversationId : undefined
  const conversationAttachmentPublicId =
    attachmentContext.kind === 'conversation' ? attachmentContext.conversationPublicId ?? undefined : undefined
  const offlineMessageId =
    attachmentContext.kind === 'offline_message' ? attachmentContext.offlineMessageId : undefined

  return (
    <div
      data-workspace-message-id={message.id}
      data-sender-type={message.sender_type}
      data-message-status={visibleStatus ?? undefined}
      className={cn('mb-4 flex gap-2.5', isMuted && 'opacity-90', isAssistantSide ? 'flex-row-reverse' : 'flex-row')}
      onContextMenu={hasMenuActions ? handleContextMenu : undefined}
    >
      {messageMenu && (
        <div
          className="fixed z-50 min-w-28 rounded-md border border-border bg-background p-1 text-sm shadow-lg"
          style={{ left: messageMenu.x, top: messageMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          {canCopy && (
            <button
              type="button"
              className="flex w-full items-center rounded px-3 py-1.5 text-left text-foreground hover:bg-muted"
              onClick={() => {
                setMessageMenu(null)
                const selectedText = selectedTextRef.current
                selectedTextRef.current = ''
                onCopyMessage?.(message, selectedText)
              }}
            >
              {t('ws.chat.copy.action', locale)}
            </button>
          )}
          {canAddKnowledgeInspiration && (
            <button
              type="button"
              className="flex w-full items-center rounded px-3 py-1.5 text-left text-foreground hover:bg-muted"
              onClick={() => {
                setMessageMenu(null)
                onAddKnowledgeInspiration?.(message)
              }}
            >
              {locale === 'zh' ? '添加知识灵感' : 'Add inspiration'}
            </button>
          )}
          {canCreateKnowledgeDocument && (
            <button
              type="button"
              className="flex w-full items-center rounded px-3 py-1.5 text-left text-foreground hover:bg-muted"
              onClick={() => {
                setMessageMenu(null)
                onCreateKnowledgeDocument?.(message)
              }}
            >
              {locale === 'zh' ? '新建知识文档' : 'Create knowledge document'}
            </button>
          )}
          {canCreateRobotQa && (
            <button
              type="button"
              className="flex w-full items-center rounded px-3 py-1.5 text-left text-foreground hover:bg-muted"
              onClick={() => {
                setMessageMenu(null)
                onCreateRobotQa?.(message)
              }}
            >
              {locale === 'zh' ? '新建机器人 QA' : 'Create robot QA'}
            </button>
          )}
          {canQuote && (
            <button
              type="button"
              className="flex w-full items-center rounded px-3 py-1.5 text-left text-foreground hover:bg-muted"
              onClick={() => {
                setMessageMenu(null)
                onQuoteMessage?.(message)
              }}
            >
              {t('ws.chat.quote.action', locale)}
            </button>
          )}
          {canRecall && (
            <button
              type="button"
              className="flex w-full items-center rounded px-3 py-1.5 text-left text-foreground hover:bg-muted"
              onClick={() => {
                setMessageMenu(null)
                onRecallMessage?.(message)
              }}
            >
              {t('ws.chat.recall.action', locale)}
            </button>
          )}
        </div>
      )}
      {isAssistantSide ? (
        showAssistantAvatar
          ? <AgentAvatar avatar={message.sender_avatar} name={message.sender_name} isBot={isBot} muted={isMuted} />
          : null
      ) : message.sender_type !== 'visitor' || showVisitorAvatar ? (
        <VisitorAvatar char={visitorChar} color={visitorColor} />
      ) : null}
      <div className={cn('flex min-w-0 max-w-[70%] flex-col', isAssistantSide ? 'items-end' : 'items-start')}>
        {(displayTimestamp || senderLabel) && (
          <div className={cn(
            'mb-1 flex max-w-full items-center gap-1 text-[11px]',
            isAssistantSide && 'justify-end text-right',
          )}>
            {displayTimestamp && (
              <span className="shrink-0 text-[#999999]" title={fullTimeTitle}>{shortTime}</span>
            )}
            {senderLabel && (
              <span className="min-w-0 truncate text-[#737373]" title={senderLabel}>{senderLabel}</span>
            )}
          </div>
        )}
        <div className={cn(visibleStatus ? 'flex min-w-0 max-w-full items-end gap-1' : 'contents')}>
          {visibleStatus && <MessageStatusIcon status={visibleStatus} locale={locale} />}
          {attachmentContentType ? (
            <div className="flex min-w-0 max-w-full flex-col">
              {quoteBlock}
              <MessageAttachment
                conversationId={conversationAttachmentId}
                conversationPublicId={conversationAttachmentPublicId}
                offlineMessageId={offlineMessageId}
                contentType={attachmentContentType}
                content={message.content}
                imageGallery={attachmentContentType === 'image' ? imageGallery : undefined}
                currentImageId={attachmentContentType === 'image' ? String(message.id) : undefined}
                inlinePlayableVideo={inlinePlayableVideo}
              />
            </div>
          ) : isRichText ? (
            quote ? (
              <div className={bubbleClassName}>
                {embeddedQuoteBlock}
                <RichTextMessageContent
                  html={message.content}
                  conversationId={conversationAttachmentId}
                  conversationPublicId={conversationAttachmentPublicId}
                  className="max-w-full text-sm leading-normal break-words break-all text-[#1a1a1a]"
                />
              </div>
            ) : (
              <RichTextMessageContent
                html={message.content}
                conversationId={conversationAttachmentId}
                conversationPublicId={conversationAttachmentPublicId}
                className={bubbleClassName}
              />
            )
          ) : hasOpenAgentTrace ? (
            <div className="w-full min-w-0 space-y-2">
              {quoteBlock}
              <OpenAgentTraceBlocks
                textBlocks={textBlocks}
                thinkingBlocks={thinkingBlocks}
                toolBlocks={visibleToolBlocks}
                locale={locale}
              />
              {textBlocks.length === 0 && <OpenAgentTextBlockView content={message.content} />}
            </div>
          ) : (
            <div
              className={cn(
                bubbleClassName,
                'whitespace-pre-wrap',
                isBot && [markdownTextRootClass, richTextListStyleClass],
              )}
            >
              {embeddedQuoteBlock}
              {isBot ? (
                <MarkdownText>{stripOpenAgentThinkSections(message.content)}</MarkdownText>
              ) : (
                <LinkifiedText content={message.content} />
              )}
            </div>
          )}
        </div>
        {failedStatusText && (
          <div
            className={cn(
              'mt-1 flex items-center gap-1 text-[11px] text-[#999999]',
              isAssistantSide && 'flex-row-reverse text-right',
            )}
          >
            {message.status === 'failed' && onRetryMessage ? (
              <button
                type="button"
                className="text-destructive hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                onClick={() => onRetryMessage(message)}
              >
                {failedStatusText}
              </button>
            ) : (
              <span className="text-destructive">{failedStatusText}</span>
            )}
          </div>
        )}
        {isBot && (
          <OpenAgentFeedbackStatus
            messageId={message.id}
            senderType={message.sender_type}
            metadata={message.metadata}
            locale={locale}
            align="end"
          />
        )}
      </div>
    </div>
  )
}
