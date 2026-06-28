'use client'

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent } from 'react'
import { MessagePrimitive, ThreadPrimitive, type MessageState } from '@assistant-ui/react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useAgentChatConfig,
  type AgentMessageMeta,
} from './agent-chat-runtime'
import { AgentComposer, type ComposerInsertRequest } from './agent-composer'
import {
  IconArrowsExchange2,
  IconLock,
  IconLockOpen,
  IconTicket,
  IconX,
  IconLoader2,
  IconMessagePlus,
  IconPinned,
  IconUserPlus,
} from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/context/auth-store'
import { useChatStore } from '@/context/chat-store'
import { useLocaleStore, type Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { EndConversationModal } from '@/app/components/features/chat/end-conversation-modal'
import { TransferConversationModal } from '@/app/components/features/chat/transfer-conversation-modal'
import { InviteCollaboratorModal } from '@/app/components/features/chat/invite-collaborator-modal'
import { MessageAttachment } from '@/app/components/features/chat/message-attachment'
import { MessageQuoteBlock } from '@/app/components/features/chat/message-quote'
import { OpenAgentFeedbackStatus } from '@/app/components/features/chat/open-agent-feedback'
import { RichTextMessageContent } from '@/app/components/features/chat/rich-text-message-content'
import {
  OpenAgentTextBlockView,
  OpenAgentTraceBlocks,
  getOpenAgentTextBlocks,
  getOpenAgentThinkingBlocks,
  getVisibleOpenAgentToolBlocks,
} from '@/app/components/features/chat/open-agent-trace-blocks'
import { conversationKeys, setVisitorWebStatusQueryData, useVisitorWebStatus } from '@/service/use-conversations'
import { get } from '@/service/base'
import { AssistantMarkdownText, MarkdownText, markdownTextRootClass } from '@/components/assistant-ui/markdown-text'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { SafeHtml } from '@/components/safe-html'
import { resolveOpenAgentHandoffEventLabel } from '@/lib/open-agent-handoff-event'
import { isLeaveMessagePromptMessage } from '@/lib/offline-message-event'
import {
  getWorkspaceAgentAvatarLetter,
  sanitizeWorkspaceAgentEventContent,
  resolveWorkspaceSystemEventContent,
} from '@/lib/workspace-agent-display'
import { isConversationHistoryContentMessage } from '@/lib/conversation-history-message'
import {
  canQuoteMessage,
  messageQuoteFromMetadata,
} from '@/lib/message-quote'
import { isWelcomeLikeContentType } from '@/lib/welcome-message-content-type'
import type {
  Conversation,
  Message,
  MessageListResponse,
  VisitorWebStatus,
  VisitorWebStatusResponse,
  WorkspaceConversationHistoryItem,
} from '@/models/conversation'
import type { Socket } from 'socket.io-client'

// ─── Timestamp formatting ────────────────────────────────────────

function formatMessageTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function formatHistoryTime(dateStr: string | null, locale: string): string {
  if (!dateStr) return locale === 'zh' ? '历史会话' : 'History'
  const d = new Date(dateStr)
  const date = d.toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    month: '2-digit',
    day: '2-digit',
  })
  const time = d.toLocaleTimeString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  return `${date} ${time}`
}

function readStatusLabel(status: string | undefined, locale: Locale): string | null {
  if (status === 'unread') return locale === 'zh' ? '未读' : 'Unread'
  if (status === 'read') return locale === 'zh' ? '已读' : 'Read'
  return null
}

function isReadStatusContentType(contentType: string | undefined): boolean {
  return contentType === 'text'
    || contentType === 'rich_text'
    || contentType === 'image'
    || contentType === 'file'
}

const MESSAGE_RECALL_WINDOW_MS = 2 * 60 * 1000

function isRecallableContentType(contentType: string | undefined): boolean {
  return contentType === 'text'
    || contentType === 'rich_text'
    || contentType === 'image'
    || contentType === 'file'
}

function isMessageWithinRecallWindow(createdAt: Date | undefined): boolean {
  if (!createdAt) return false
  return Date.now() - createdAt.getTime() <= MESSAGE_RECALL_WINDOW_MS
}

function recalledMessageText(input: {
  locale: string
  isOwn?: boolean
  senderType?: string
  senderName?: string | null
}): string {
  const { locale, isOwn, senderType, senderName } = input
  if (isOwn) return t('ws.chat.recall.youRecalled', locale as Locale)
  if (senderType === 'visitor') return t('ws.chat.recall.visitorRecalled', locale as Locale)
  if (senderName) return t('ws.chat.recall.namedRecalled', locale as Locale, { name: senderName })
  return t('ws.chat.recall.otherRecalled', locale as Locale)
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
      <div className="max-w-full rounded-[18px] border border-dashed border-[#D8D8D8] bg-[#F5F5F5] px-3.5 py-2 text-sm leading-normal text-[#737373]">
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
      {time && (
        <span className="mt-1 text-[11px] text-[#999999]">{time}</span>
      )}
    </div>
  )
}

function SystemAgentAvatar({
  className,
  muted = false,
}: {
  className?: string
  muted?: boolean
}) {
  return (
    <div
      className={cn(
        'flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium',
        muted ? 'bg-[#E8E8E8] text-[#737373]' : 'bg-[#D6E6F9] text-[#4A80B5]',
        className,
      )}
    >
      s
    </div>
  )
}

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
      {avatar ? (
        <img
          src={avatar}
          alt={name || label}
          className="h-full w-full object-cover"
        />
      ) : (
        label
      )}
    </div>
  )
}

function AgentSideWelcomeBubble({
  content,
  time,
  muted = false,
}: {
  content: string
  time: string
  muted?: boolean
}) {
  return (
    <div className="mb-4 flex flex-row-reverse gap-2.5">
      <SystemAgentAvatar muted={muted} />
      <div className="flex min-w-0 max-w-[70%] flex-col items-end">
        <SafeHtml
          html={content}
          className={cn(
            'max-w-full rounded-[18px] px-3.5 py-2.5 text-sm leading-normal break-words break-all whitespace-pre-wrap text-[#1a1a1a]',
            muted ? 'bg-[#E8E8E8]' : 'bg-[#DBEAFE]',
            richTextListStyleClass,
          )}
        />
        <span className="mt-1 text-right text-[11px] text-[#999999]">{time}</span>
      </div>
    </div>
  )
}

const internalNoteBubbleClass = 'border border-[#F4C35E] bg-[#FFE6A6]'
const EMPTY_MESSAGES: Message[] = []

function scrollToWorkspaceMessage(messageId: number, locale: Locale): void {
  const node = document.querySelector<HTMLElement>(`[data-workspace-message-id="${messageId}"]`)
  if (!node) {
    window.alert(t('ws.chat.quote.locateFailed', locale))
    return
  }
  node.scrollIntoView({ block: 'center', behavior: 'smooth' })
  node.classList.add('bg-warning/15')
  window.setTimeout(() => node.classList.remove('bg-warning/15'), 2000)
}

function isCollaborativeConversation(conversation: Conversation): boolean {
  return (
    conversation.viewer_relation === 'collaborator'
    || conversation.collaborated_by_current_user === true
    || Boolean(conversation.collaborators?.length)
  )
}

// ─── Agent-side message bubble ───────────────────────────────────

function AgentMessageBubble({
  message,
  socket,
  onComposerInsertRequest,
}: {
  message: MessageState
  socket: Socket | null
  onComposerInsertRequest?: (request: Omit<ComposerInsertRequest, 'id'>) => void
}) {
  const {
    conversation,
    imageMessages,
    locale: cfgLocale,
    readStatusEnabled,
    isClosed,
    canSendPublicReply,
    onQuoteMessage,
  } = useAgentChatConfig()
  const meta = message.metadata?.custom as AgentMessageMeta | undefined
  const [messageMenu, setMessageMenu] = useState<{ x: number; y: number } | null>(null)
  const conversationMessages = useChatStore((state) => state.messages.get(conversation.id) || EMPTY_MESSAGES)
  const isAgent = meta?.senderType === 'agent'
  const isBot = meta?.senderType === 'bot'
  const isInternalNote = meta?.contentType === 'internal_note'
  const isAssistantSide = isAgent || isBot
  const isSystem = message.role === 'system' || meta?.senderType === 'system'
  const visitorAvatarBg = conversation.visitor?.avatar_color || '#4A8C5C'
  const visitorAvatarChar = (conversation.visitor?.name || '访').charAt(0)

  const firstPart = message.content?.[0]
  let content = ''
  if (firstPart) {
    if ('text' in firstPart) content = firstPart.text as string
    else if ('image' in firstPart) content = firstPart.image as string
  }
  const attachmentContentType =
    meta?.contentType === 'image' ? 'image' : meta?.contentType === 'file' ? 'file' : null
  const isRichText = meta?.contentType === 'rich_text'
  const textBlocks = isBot ? getOpenAgentTextBlocks(meta?.metadata) : []
  const thinkingBlocks = isBot ? getOpenAgentThinkingBlocks(meta?.metadata) : []
  const visibleToolBlocks = isBot ? getVisibleOpenAgentToolBlocks(meta?.metadata) : []
  const hasOpenAgentTrace =
    isBot && (textBlocks.length > 0 || thinkingBlocks.length > 0 || visibleToolBlocks.length > 0)
  const hasMessageText = content.trim().length > 0
  const showSenderName = Boolean(
    meta?.senderName && (isBot || (isAgent && isCollaborativeConversation(conversation))),
  )
  const readStatusText = readStatusEnabled
    && isAgent
    && meta?.isOwn
    && isReadStatusContentType(meta?.contentType)
    ? readStatusLabel(meta?.messageStatus, cfgLocale)
    : null
  const isRecalled = Boolean(meta?.isRecalled || meta?.metadata?.is_recalled)
  const canRecallMessage =
    Boolean(socket)
    && !isRecalled
    && !isClosed
    && canSendPublicReply
    && meta?.isOwn
    && isRecallableContentType(meta?.contentType)
    && String(conversation.channel?.channel_type || '').toLowerCase() === 'web'
    && isMessageWithinRecallWindow(message.createdAt)
  const originalMessage = useMemo<Message>(() => ({
    id: Number(message.id) || 0,
    conversation_id: meta?.conversationId ?? conversation.id,
    sender_type: (meta?.senderType || 'system') as Message['sender_type'],
    sender_id: meta?.senderId ?? null,
    sender_name: meta?.senderName ?? null,
    sender_avatar: meta?.senderAvatar ?? null,
    content_type: (meta?.contentType || 'text') as Message['content_type'],
    content,
    is_recalled: isRecalled,
    recalled_at: meta?.recalledAt ?? null,
    recalled_by_type: meta?.recalledByType ?? null,
    recalled_by_name: meta?.recalledByName ?? null,
    metadata: meta?.metadata,
    created_at: message.createdAt?.toISOString() || new Date().toISOString(),
  }), [
    content,
    conversation.id,
    isRecalled,
    message.createdAt,
    message.id,
    meta?.contentType,
    meta?.conversationId,
    meta?.metadata,
    meta?.recalledAt,
    meta?.recalledByName,
    meta?.recalledByType,
    meta?.senderAvatar,
    meta?.senderId,
    meta?.senderName,
    meta?.senderType,
  ])
  const canQuoteCurrentMessage =
    Boolean(socket)
    && canQuoteMessage(originalMessage, {
      canSend: canSendPublicReply,
      closed: isClosed,
      webChannel: String(conversation.channel?.channel_type || '').toLowerCase() === 'web',
    })
  const quote = messageQuoteFromMetadata(meta?.metadata)
  const quotedOriginal = quote
    ? conversationMessages.find((item) => item.id === quote.message_id) ?? null
    : null
  const reeditQuotedMessage =
    quotedOriginal && canQuoteMessage(quotedOriginal, {
      canSend: canSendPublicReply,
      closed: isClosed,
      webChannel: String(conversation.channel?.channel_type || '').toLowerCase() === 'web',
    })
      ? quotedOriginal
      : null
  const handleQuoteClick = quote
    ? () => scrollToWorkspaceMessage(quote.message_id, cfgLocale)
    : undefined
  const quoteAttachmentContext = {
    conversationId: meta?.conversationId ?? conversation.id,
  }
  const quoteBlock = quote ? (
    <MessageQuoteBlock
      quote={quote}
      locale={cfgLocale}
      original={quotedOriginal}
      onClick={handleQuoteClick}
      attachmentContext={quoteAttachmentContext}
      className="max-w-full rounded-lg"
    />
  ) : null
  const embeddedQuoteBlock = quote ? (
    <MessageQuoteBlock
      quote={quote}
      locale={cfgLocale}
      original={quotedOriginal}
      onClick={handleQuoteClick}
      variant="embedded"
      attachmentContext={quoteAttachmentContext}
      className="mb-2"
    />
  ) : null
  const bubbleClassName = cn(
    'max-w-full rounded-[18px] px-3.5 py-2.5 text-sm leading-normal break-words break-all text-[#1a1a1a]',
    isInternalNote
      ? internalNoteBubbleClass
      : isAssistantSide ? 'bg-[#DBEAFE]' : 'border border-[#E0E0E0] bg-[#F0F0F0]',
  )
  const recallEditContent = typeof meta?.metadata?.recall_edit_content === 'string'
    ? meta.metadata.recall_edit_content
    : ''
  const canEditRecalled =
    isRecalled
    && meta?.isOwn
    && canSendPublicReply
    && !isClosed
    && (meta?.contentType === 'text' || meta?.contentType === 'rich_text')
    && recallEditContent.length > 0

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

  const handleContextMenu = useCallback((event: ReactMouseEvent<HTMLDivElement>) => {
    if (!canRecallMessage && !canQuoteCurrentMessage) return
    event.preventDefault()
    setMessageMenu({ x: event.clientX, y: event.clientY })
  }, [canQuoteCurrentMessage, canRecallMessage])

  const handleQuote = useCallback(() => {
    setMessageMenu(null)
    if (!canQuoteCurrentMessage) return
    onQuoteMessage(originalMessage)
  }, [canQuoteCurrentMessage, onQuoteMessage, originalMessage])

  const handleRecall = useCallback(() => {
    setMessageMenu(null)
    if (!socket || !canRecallMessage) return
    socket.emit(
      'recall_message',
      {
        conversation_id: conversation.id,
        message_id: Number(message.id),
      },
      (response?: { ok?: boolean; message?: string }) => {
        if (response?.ok === false) {
          window.alert(response.message || t('ws.chat.recall.failed', cfgLocale))
        }
      },
    )
  }, [canRecallMessage, cfgLocale, conversation.id, message.id, socket])

  const handleEditRecalled = useCallback(() => {
    if (!canEditRecalled || !onComposerInsertRequest) return
    onComposerInsertRequest({
      text: recallEditContent,
      contentType: meta?.contentType === 'rich_text' ? 'rich_text' : 'text',
      quotedMessage: reeditQuotedMessage,
    })
  }, [canEditRecalled, meta?.contentType, onComposerInsertRequest, recallEditContent, reeditQuotedMessage])

  if (meta?.contentType && isWelcomeLikeContentType(meta.contentType)) {
    return (
      <AgentSideWelcomeBubble
        content={content}
        time={message.createdAt ? formatMessageTime(message.createdAt.toISOString()) : ''}
      />
    )
  }

  if (meta?.contentType === 'satisfaction_event') {
    const submitted = meta.eventType === 'feedback_submitted'
    return (
      <div className="mb-4 flex justify-center py-1">
        <span
          className={cn(
            'rounded-full px-3 py-1.5 text-center text-[12px] font-medium leading-normal',
            submitted ? 'bg-[#F0FDF4] text-[#16A34A]' : 'bg-[#EFF6FF] text-[#3B82F6]',
          )}
        >
          {sanitizeWorkspaceAgentEventContent(content, cfgLocale)}
        </span>
      </div>
    )
  }

  if (isSystem && !isInternalNote && isLeaveMessagePromptMessage({ metadata: meta?.metadata })) {
    return (
      <AgentSideWelcomeBubble
        content={content}
        time={message.createdAt ? formatMessageTime(message.createdAt.toISOString()) : ''}
      />
    )
  }

  if (isSystem && !isInternalNote) {
    const handoffEventLabel = resolveOpenAgentHandoffEventLabel(meta?.metadata, cfgLocale)
    const systemContent = handoffEventLabel || content
    return (
      <div className="mb-4 flex justify-center py-1">
        <span className="text-center text-[12px] leading-normal text-[#999999]">
          {resolveWorkspaceSystemEventContent(systemContent, meta?.metadata, cfgLocale)}
        </span>
      </div>
    )
  }

  if (isBot && !attachmentContentType && !hasOpenAgentTrace && !hasMessageText) return null

  if (isRecalled) {
    return (
      <div className={cn('mb-4 flex gap-2.5', isAssistantSide ? 'flex-row-reverse' : 'flex-row')}>
        {isAssistantSide ? (
          <AgentAvatar
            avatar={meta?.senderAvatar}
            name={meta?.senderName}
            isBot={isBot}
          />
        ) : (
          <div
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white"
            style={{ backgroundColor: visitorAvatarBg }}
          >
            {visitorAvatarChar}
          </div>
        )}
        <RecalledMessageNotice
          text={recalledMessageText({
            locale: cfgLocale,
            isOwn: meta?.isOwn,
            senderType: meta?.senderType,
            senderName: meta?.senderName,
          })}
          time={message.createdAt ? formatMessageTime(message.createdAt.toISOString()) : ''}
          alignEnd={isAssistantSide}
          editLabel={canEditRecalled ? t('ws.chat.recall.editAgain', cfgLocale) : undefined}
          onEdit={canEditRecalled ? handleEditRecalled : undefined}
        />
      </div>
    )
  }

  // 2.1 pen: visitor left (#F0F0F0 + border), agent (own) right (#DBEAFE)
  return (
    <div
      className={cn('mb-4 flex gap-2.5', isAssistantSide ? 'flex-row-reverse' : 'flex-row')}
      onContextMenu={handleContextMenu}
    >
      {messageMenu && (
        <div
          className="fixed z-50 min-w-28 rounded-md border border-border bg-background p-1 text-sm shadow-lg"
          style={{ left: messageMenu.x, top: messageMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          {canQuoteCurrentMessage && (
            <button
              type="button"
              className="flex w-full items-center rounded px-3 py-1.5 text-left text-foreground hover:bg-muted"
              onClick={handleQuote}
            >
              {t('ws.chat.quote.action', cfgLocale)}
            </button>
          )}
          {canRecallMessage && (
            <button
              type="button"
              className="flex w-full items-center rounded px-3 py-1.5 text-left text-foreground hover:bg-muted"
              onClick={handleRecall}
            >
              {t('ws.chat.recall.action', cfgLocale)}
            </button>
          )}
        </div>
      )}
      {isAssistantSide ? (
        <AgentAvatar
          avatar={meta?.senderAvatar}
          name={meta?.senderName}
          isBot={isBot}
        />
      ) : (
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white"
          style={{ backgroundColor: visitorAvatarBg }}
        >
          {visitorAvatarChar}
        </div>
      )}
      <div className={cn('flex min-w-0 max-w-[70%] flex-col', isAssistantSide ? 'items-end' : 'items-start')}>
        {showSenderName && meta?.senderName && (
          <span className="mb-1 max-w-full truncate text-right text-[11px] text-[#737373]" title={meta.senderName}>
            {meta.senderName}
          </span>
        )}
        {attachmentContentType ? (
          <>
            {quoteBlock}
            <MessageAttachment
              conversationId={meta?.conversationId ?? conversation.id}
              contentType={attachmentContentType}
              content={content}
              imageGallery={attachmentContentType === 'image' ? imageMessages : undefined}
              currentImageId={attachmentContentType === 'image' ? message.id : undefined}
            />
          </>
        ) : isRichText ? (
          quote ? (
            <div className={bubbleClassName}>
              {embeddedQuoteBlock}
              <RichTextMessageContent
                html={content}
                conversationId={meta?.conversationId ?? conversation.id}
                className="max-w-full text-sm leading-normal break-words break-all text-[#1a1a1a]"
              />
            </div>
          ) : (
            <RichTextMessageContent
              html={content}
              conversationId={meta?.conversationId ?? conversation.id}
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
              locale={cfgLocale}
            />
            {textBlocks.length === 0 && (
              <OpenAgentTextBlockView content={content} />
            )}
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
              <MessagePrimitive.Parts>
                {({ part }) => (
                  part.type === 'text' || part.type === 'reasoning'
                    ? <AssistantMarkdownText />
                    : null
                )}
              </MessagePrimitive.Parts>
            ) : content}
          </div>
        )}
        {(message.createdAt || readStatusText) && (
          <div className={cn('mt-1 flex items-center gap-1 text-[11px] text-[#999999]', isAssistantSide && 'flex-row-reverse text-right')}>
            {message.createdAt && <span>{formatMessageTime(message.createdAt.toISOString())}</span>}
            {readStatusText && <span>{readStatusText}</span>}
          </div>
        )}
        {isBot && (
          <OpenAgentFeedbackStatus
            messageId={Number(message.id)}
            senderType={meta?.senderType ?? ''}
            metadata={meta?.metadata}
            locale={cfgLocale}
            align="end"
          />
        )}
      </div>
    </div>
  )
}

function ConversationDivider({ label }: { label: string }) {
  return (
    <div className="mb-4 flex justify-center text-[12px] text-[#999999]">
      <span className="shrink-0 rounded-full border border-[#E5E5E5] bg-white px-3 py-1">
        {label}
      </span>
    </div>
  )
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
      className="mx-auto mb-4 flex items-center gap-1 rounded-full px-4 py-1.5 text-[12px] font-medium text-[#1a1a1a] transition-colors hover:bg-black/[0.04] disabled:cursor-not-allowed disabled:text-[#999999]"
      onClick={onClick}
      disabled={disabled || loading}
      type="button"
    >
      {loading && <IconLoader2 size={14} className="animate-spin" />}
      {label}
    </button>
  )
}

function AgentHistoryMessageBubble({
  message,
  locale,
  visitorAvatarBg,
  visitorAvatarChar,
  imageMessages,
  allMessages,
  readStatusEnabled,
  currentUserId,
}: {
  message: Message
  locale: string
  visitorAvatarBg: string
  visitorAvatarChar: string
  imageMessages: { id: string; content: string }[]
  allMessages: Message[]
  readStatusEnabled: boolean
  currentUserId?: number | null
}) {
  const isAgent = message.sender_type === 'agent' || message.sender_type === 'bot'
  const isBot = message.sender_type === 'bot'
  const isSystem = message.sender_type === 'system'
  const isInternalNote = message.content_type === 'internal_note'
  const attachmentContentType =
    message.content_type === 'image' ? 'image' : message.content_type === 'file' ? 'file' : null
  const isRichText = message.content_type === 'rich_text'
  const textBlocks = isBot ? getOpenAgentTextBlocks(message.metadata) : []
  const thinkingBlocks = isBot ? getOpenAgentThinkingBlocks(message.metadata) : []
  const visibleToolBlocks = isBot ? getVisibleOpenAgentToolBlocks(message.metadata) : []
  const hasOpenAgentTrace =
    isBot && (textBlocks.length > 0 || thinkingBlocks.length > 0 || visibleToolBlocks.length > 0)
  const hasMessageText = message.content.trim().length > 0
  const readStatusText = readStatusEnabled
    && message.sender_type === 'agent'
    && message.sender_id === currentUserId
    && isReadStatusContentType(message.content_type)
    ? readStatusLabel(message.status, locale as Locale)
    : null
  const quote = messageQuoteFromMetadata(message.metadata)
  const quotedOriginal = quote
    ? allMessages.find((item) => item.id === quote.message_id) ?? null
    : null
  const handleQuoteClick = quote
    ? () => scrollToWorkspaceMessage(quote.message_id, locale as Locale)
    : undefined
  const quoteAttachmentContext = {
    conversationId: message.conversation_id,
  }
  const quoteBlock = quote ? (
    <MessageQuoteBlock
      quote={quote}
      locale={locale as Locale}
      original={quotedOriginal}
      onClick={handleQuoteClick}
      attachmentContext={quoteAttachmentContext}
      className="max-w-full rounded-lg"
    />
  ) : null
  const embeddedQuoteBlock = quote ? (
    <MessageQuoteBlock
      quote={quote}
      locale={locale as Locale}
      original={quotedOriginal}
      onClick={handleQuoteClick}
      variant="embedded"
      attachmentContext={quoteAttachmentContext}
      className="mb-2"
    />
  ) : null
  const historyBubbleClassName = cn(
    'max-w-full rounded-[18px] px-3.5 py-2.5 text-sm leading-normal break-words break-all text-[#1a1a1a]',
    isInternalNote
      ? internalNoteBubbleClass
      : isAgent ? 'bg-[#E8E8E8]' : 'border border-[#E0E0E0] bg-white',
  )

  if (message.is_recalled) {
    return (
      <div className={cn('mb-4 flex gap-2.5 opacity-90', isAgent ? 'flex-row-reverse' : 'flex-row')}>
        {isAgent ? (
          <AgentAvatar
            avatar={message.sender_avatar}
            name={message.sender_name}
            isBot={isBot}
            muted
          />
        ) : (
          <div
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white"
            style={{ backgroundColor: visitorAvatarBg }}
          >
            {visitorAvatarChar}
          </div>
        )}
        <RecalledMessageNotice
          text={recalledMessageText({
            locale,
            isOwn: message.sender_type === 'agent' && message.sender_id === currentUserId,
            senderType: message.sender_type,
            senderName: message.sender_name,
          })}
          time={formatMessageTime(message.created_at)}
          alignEnd={isAgent}
        />
      </div>
    )
  }

  if (isWelcomeLikeContentType(message.content_type)) {
    return (
      <AgentSideWelcomeBubble
        content={message.content}
        time={formatMessageTime(message.created_at)}
        muted
      />
    )
  }

  if (message.content_type === 'satisfaction_event') {
    const submitted = message.event_type === 'feedback_submitted'
    return (
      <div className="mb-4 flex justify-center py-1">
        <span
          className={cn(
            'rounded-full px-3 py-1.5 text-center text-[12px] font-medium leading-normal',
            submitted ? 'bg-[#F0FDF4] text-[#16A34A]' : 'bg-[#EFF6FF] text-[#3B82F6]',
          )}
        >
          {sanitizeWorkspaceAgentEventContent(message.content, locale)}
        </span>
      </div>
    )
  }

  if (isSystem && !isInternalNote && isLeaveMessagePromptMessage(message)) {
    return (
      <AgentSideWelcomeBubble
        content={message.content}
        time={formatMessageTime(message.created_at)}
        muted
      />
    )
  }

  if (isSystem && !isInternalNote) {
    const handoffEventLabel = resolveOpenAgentHandoffEventLabel(message.metadata, locale)
    const systemContent = handoffEventLabel || message.content
    return (
      <div className="mb-4 flex justify-center py-1">
        <span className="text-center text-[12px] leading-normal text-[#999999]">
          {resolveWorkspaceSystemEventContent(systemContent, message.metadata, locale)}
        </span>
      </div>
    )
  }

  if (isBot && !attachmentContentType && !hasOpenAgentTrace && !hasMessageText) return null

  return (
    <div className={cn('mb-4 flex gap-2.5 opacity-90', isAgent ? 'flex-row-reverse' : 'flex-row')}>
      {isAgent ? (
        <AgentAvatar
          avatar={message.sender_avatar}
          name={message.sender_name}
          isBot={isBot}
          muted
        />
      ) : (
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white"
          style={{ backgroundColor: visitorAvatarBg }}
        >
          {visitorAvatarChar}
        </div>
      )}
      <div className={cn('flex min-w-0 max-w-[70%] flex-col', isAgent ? 'items-end' : 'items-start')}>
        {isBot && message.sender_name && (
          <span className="mb-1 text-[11px] text-[#737373]">{message.sender_name}</span>
        )}
        {attachmentContentType ? (
          <>
            {quoteBlock}
            <MessageAttachment
              conversationId={message.conversation_id}
              contentType={attachmentContentType}
              content={message.content}
              imageGallery={attachmentContentType === 'image' ? imageMessages : undefined}
              currentImageId={attachmentContentType === 'image' ? String(message.id) : undefined}
            />
          </>
        ) : isRichText ? (
          quote ? (
            <div className={historyBubbleClassName}>
              {embeddedQuoteBlock}
              <RichTextMessageContent
                html={message.content}
                conversationId={message.conversation_id}
                className="max-w-full text-sm leading-normal break-words break-all text-[#1a1a1a]"
              />
            </div>
          ) : (
            <RichTextMessageContent
              html={message.content}
              conversationId={message.conversation_id}
              className={historyBubbleClassName}
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
            {textBlocks.length === 0 && (
              <OpenAgentTextBlockView content={message.content} />
            )}
          </div>
        ) : (
          <div
            className={cn(
              historyBubbleClassName,
              'whitespace-pre-wrap',
              isBot && [markdownTextRootClass, richTextListStyleClass],
            )}
          >
            {embeddedQuoteBlock}
            {isBot ? <MarkdownText>{message.content}</MarkdownText> : message.content}
          </div>
        )}
        <div className={cn('mt-1 flex items-center gap-1 text-[11px] text-[#999999]', isAgent && 'flex-row-reverse text-right')}>
          <span>{formatMessageTime(message.created_at)}</span>
          {readStatusText && <span>{readStatusText}</span>}
        </div>
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

function HistoryConversationBlock({
  conversation,
  locale,
  visitorAvatarBg,
  visitorAvatarChar,
  highlightedMessageId,
  readStatusEnabled,
  currentUserId,
}: {
  conversation: WorkspaceConversationHistoryItem
  locale: string
  visitorAvatarBg: string
  visitorAvatarChar: string
  highlightedMessageId: number | null
  readStatusEnabled: boolean
  currentUserId?: number | null
}) {
  const visibleMessages = useMemo(
    () => conversation.messages.filter(isConversationHistoryContentMessage),
    [conversation.messages],
  )
  const imageMessages = useMemo(
    () =>
      visibleMessages
        .filter((msg) => msg.content_type === 'image' && !msg.is_recalled)
        .map((msg) => ({ id: String(msg.id), content: msg.content })),
    [visibleMessages],
  )
  const time = formatHistoryTime(
    conversation.started_at || conversation.created_at || conversation.last_message_at,
    locale,
  )
  const channel = conversation.channel?.name || conversation.channel?.channel_type || '-'
  const label = locale === 'zh'
    ? `${time} 历史会话 · ${channel}`
    : `${time} History · ${channel}`

  return (
    <div>
      <ConversationDivider label={label} />
      <p className="mb-3 text-center text-[11px] text-[#999999]">
        {locale === 'zh' ? '历史会话仅供查看' : 'History is read-only'}
      </p>
      {conversation.messages_truncated && (
        <div className="mb-3 text-center text-[12px] text-[#999999]">
          {locale === 'zh' ? '仅显示最近 200 条消息' : 'Showing latest 200 messages'}
        </div>
      )}
      {visibleMessages.map((message) => (
        <div
          key={message.id}
          data-workspace-message-id={message.id}
          className={cn(
            'rounded-2xl transition-colors duration-300',
            highlightedMessageId === message.id && 'bg-warning/15',
          )}
        >
          <AgentHistoryMessageBubble
            message={message}
            locale={locale}
            visitorAvatarBg={visitorAvatarBg}
            visitorAvatarChar={visitorAvatarChar}
            imageMessages={imageMessages}
            allMessages={visibleMessages}
            readStatusEnabled={readStatusEnabled}
            currentUserId={currentUserId}
          />
        </div>
      ))}
    </div>
  )
}

function visitorWebStatusLabel(status: VisitorWebStatus, locale: Locale): string {
  if (status === 'online') return t('ws.chat.visitorWebStatusOnline', locale)
  if (status === 'offline') return t('ws.chat.visitorWebStatusOffline', locale)
  return t('ws.chat.visitorWebStatusUnknown', locale)
}

function visitorWebStatusTooltip(status: VisitorWebStatus, locale: Locale): string {
  if (status === 'unknown') return t('ws.chat.visitorWebStatusUnavailable', locale)
  return t('ws.chat.visitorWebStatusTooltip', locale, {
    status: visitorWebStatusLabel(status, locale),
  })
}

function shouldShowVisitorWebStatus(conversation: Conversation): boolean {
  return (
    String(conversation.channel?.channel_type || '').toLowerCase() === 'web'
    && Boolean(conversation.visitor?.external_id)
  )
}

function VisitorWebStatusBadge({
  conversation,
  socket,
}: {
  conversation: Conversation
  socket: Socket | null
}) {
  const { locale } = useLocaleStore()
  const queryClient = useQueryClient()
  const visible = conversation.status !== 'closed' && shouldShowVisitorWebStatus(conversation)
  const statusQuery = useVisitorWebStatus(conversation.id, {
    enabled: visible,
    refetchInterval: 5_000,
  })

  useEffect(() => {
    if (!socket || !visible) return

    const handleStatusUpdated = (payload: VisitorWebStatusResponse) => {
      if (payload.conversation_id !== conversation.id) return
      setVisitorWebStatusQueryData(queryClient, payload)
    }

    const handleConnect = () => {
      queryClient.invalidateQueries({
        queryKey: conversationKeys.visitorWebStatus(conversation.id),
      })
    }

    socket.on('visitor_web_status_updated', handleStatusUpdated)
    socket.on('connect', handleConnect)
    return () => {
      socket.off('visitor_web_status_updated', handleStatusUpdated)
      socket.off('connect', handleConnect)
    }
  }, [conversation.id, queryClient, socket, visible])

  if (!visible) return null

  if (statusQuery.isLoading && !statusQuery.data) {
    const label = t('ws.chat.visitorWebStatusChecking', locale)
    return (
      <span
        aria-label={label}
        className="inline-flex h-[22px] w-14 shrink-0 items-center rounded-full bg-muted px-2"
        title={label}
      >
        <span className="h-2 w-full animate-pulse rounded-full bg-muted-foreground/20" />
      </span>
    )
  }

  if (statusQuery.data && !statusQuery.data.can_display) return null

  const status: VisitorWebStatus = statusQuery.isError
    ? 'unknown'
    : statusQuery.data?.status ?? 'unknown'
  const label = visitorWebStatusLabel(status, locale)
  const tooltip = visitorWebStatusTooltip(status, locale)
  const online = status === 'online'

  return (
    <span
      aria-label={tooltip}
      className={cn(
        'inline-flex h-[22px] max-w-24 shrink-0 items-center gap-1.5 rounded-full border px-2 text-[12px] font-medium',
        online
          ? 'border-success/20 bg-success/10 text-success'
          : 'border-border bg-muted text-muted-foreground',
      )}
      title={tooltip}
    >
      <span
        className={cn(
          'h-1.5 w-1.5 shrink-0 rounded-full',
          online ? 'bg-success' : 'bg-muted-foreground/70',
        )}
      />
      <span className="min-w-0 truncate">{label}</span>
    </span>
  )
}

// ─── Main Thread ─────────────────────────────────────────────────

type AgentThreadProps = {
  socket: Socket | null
  composerInsertRequest?: ComposerInsertRequest | null
  onComposerInsertRequest?: (request: Omit<ComposerInsertRequest, 'id'>) => void
  composerInputHeight?: number
  onComposerInputHeightCommit?: (height: number) => void
  messageSearchOpen?: boolean
  onOpenMessageSearch?: () => void
  messageSearchTarget?: {
    conversationId: number
    messageId: number
    requestId: number
  } | null
}

export function AgentThread({
  socket,
  composerInsertRequest,
  onComposerInsertRequest,
  composerInputHeight,
  onComposerInputHeightCommit,
  messageSearchOpen,
  onOpenMessageSearch,
  messageSearchTarget,
}: AgentThreadProps) {
  const {
    conversation,
    isClosed,
    isTyping,
    visitorTypingContent,
    hasMore,
    loadingMore,
    historyAvailable,
    historyConversations,
    historyHasMore,
    historyLoading,
    historyLoaded,
    historyError,
    historyLimitReached,
    onLoadMore,
    onLoadHistory,
    onEndConversation,
    onCreateTicket,
    canCreateTicket,
    canPinConversation,
    pinningConversation,
    onTogglePinConversation,
    canLockConversationTimeout,
    lockingConversationTimeout,
    onToggleConversationTimeoutLock,
    canTransfer,
    canEndConversation,
    canInviteCollaborator,
    canStartNewConversation,
    startNewConversationDisabledReason,
    startingNewConversation,
    onStartNewConversation,
    onTransferred,
    onCollaborationInvitationSent,
    readStatusEnabled,
  } = useAgentChatConfig()
  const { locale } = useLocaleStore()
  const currentUserId = useAuthStore((state) => state.user?.id)
  const currentMessages = useChatStore((state) => state.messages.get(conversation.id) || EMPTY_MESSAGES)
  const [showEndModal, setShowEndModal] = useState(false)
  const [showTransferModal, setShowTransferModal] = useState(false)
  const [showInviteModal, setShowInviteModal] = useState(false)
  const [highlightedMessageId, setHighlightedMessageId] = useState<number | null>(null)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const pendingScrollDeltaRef = useRef<number | null>(null)
  const isNearBottomRef = useRef(true)
  const loadedSearchTargetRef = useRef<string | null>(null)
  const lastTailMessageRef = useRef<{ conversationId: number; messageId: number | null }>({
    conversationId: conversation.id,
    messageId: null,
  })
  const visitorAvatarBg = conversation.visitor?.avatar_color || '#4A8C5C'
  const visitorAvatarChar = (conversation.visitor?.name || '访').charAt(0)
  const latestMessage = currentMessages[currentMessages.length - 1]
  const latestMessageId = latestMessage?.id ?? null
  const isPeerConversation = conversation.viewer_relation === 'peer'
  const isCollaboratorConversation = conversation.viewer_relation === 'collaborator'
  const ownerName = conversation.agent?.display_name || conversation.agent?.name
  const collaboratorNames = (conversation.collaborators ?? [])
    .map((agent) => agent.display_name || agent.name)
    .filter(Boolean)
  const visibleHistoryConversations = useMemo(
    () => historyConversations.filter((item) => item.messages.some(isConversationHistoryContentMessage)),
    [historyConversations],
  )
  const oldestHistoryId = historyConversations[0]?.id
  const showHistoryEntry = historyAvailable && !historyLoaded
  const showCurrentDivider = historyLoaded && visibleHistoryConversations.length > 0
  const showHistoryDone =
    historyLoaded && visibleHistoryConversations.length > 0 && (!historyHasMore || historyLimitReached)
  const historyEndTime = formatHistoryTime(
    conversation.ended_at || conversation.last_message_at || conversation.created_at,
    locale,
  )
  const pinLabel = conversation.is_pinned
    ? t('ws.chat.unpinConversation', locale)
    : t('ws.chat.pinConversation', locale)
  const timeoutLockLabel = conversation.is_timeout_locked
    ? t('ws.chat.unlockConversationTimeout', locale)
    : t('ws.chat.lockConversationTimeout', locale)

  const loadHistoryWithAnchor = useCallback(
    async (beforeId?: number) => {
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

  const updateNearBottom = useCallback(() => {
    const viewport = viewportRef.current
    if (!viewport) return
    isNearBottomRef.current = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight < 80
  }, [])

  const scrollToBottom = useCallback((behavior: ScrollBehavior) => {
    const scroll = () => {
      const viewport = viewportRef.current
      if (!viewport) return
      viewport.scrollTo({ top: viewport.scrollHeight, behavior })
      isNearBottomRef.current = true
    }

    scroll()
    window.requestAnimationFrame(scroll)
  }, [])

  useLayoutEffect(() => {
    const previousTail = lastTailMessageRef.current
    const conversationChanged = previousTail.conversationId !== conversation.id
    const tailChanged = conversationChanged || previousTail.messageId !== latestMessageId

    lastTailMessageRef.current = {
      conversationId: conversation.id,
      messageId: latestMessageId,
    }

    if (!latestMessage || !tailChanged) return

    if (conversationChanged || previousTail.messageId == null) {
      scrollToBottom('auto')
      return
    }

    const isOwnAgentMessage =
      latestMessage.sender_type === 'agent' && latestMessage.sender_id === currentUserId
    if (isOwnAgentMessage || isNearBottomRef.current) {
      scrollToBottom('smooth')
    }
  }, [
    conversation.id,
    currentUserId,
    latestMessage,
    latestMessageId,
    scrollToBottom,
  ])

  useEffect(() => {
    if (!messageSearchTarget || messageSearchTarget.conversationId !== conversation.id) return
    const key = `${messageSearchTarget.requestId}:${messageSearchTarget.messageId}`
    const selector = `[data-workspace-message-id="${messageSearchTarget.messageId}"]`

    const scrollToTarget = () => {
      const node = viewportRef.current?.querySelector<HTMLElement>(selector)
      if (!node) return false
      node.scrollIntoView({ block: 'center', behavior: 'smooth' })
      setHighlightedMessageId(messageSearchTarget.messageId)
      window.setTimeout(() => {
        setHighlightedMessageId((current) => (
          current === messageSearchTarget.messageId ? null : current
        ))
      }, 2000)
      return true
    }

    window.requestAnimationFrame(() => {
      if (scrollToTarget()) return
      if (loadedSearchTargetRef.current === key) return
      loadedSearchTargetRef.current = key
      get<MessageListResponse>(`v1/conversations/${conversation.id}/messages`, {
        searchParams: { before_id: messageSearchTarget.messageId + 1, limit: 20 },
      })
        .then((data) => {
          const merged = [...data.items, ...currentMessages]
          const seen = new Set<number>()
          const nextMessages = merged
            .filter((message) => {
              if (seen.has(message.id)) return false
              seen.add(message.id)
              return true
            })
            .sort((a, b) => a.id - b.id)
          useChatStore.getState().setMessages(conversation.id, nextMessages)
          window.requestAnimationFrame(() => {
            if (!scrollToTarget()) {
              window.alert(t('ws.chat.messageSearch.locateFailed', locale))
            }
          })
        })
        .catch(() => {
          window.alert(t('ws.chat.messageSearch.locateFailed', locale))
        })
    })
  }, [conversation.id, currentMessages, locale, messageSearchTarget])

  return (
    <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col bg-[#FAFAFA]">
      {/* 会话头部 — 2.1 pen: #FAFAFA, 56px, px 24 */}
      <div className="mt-px flex h-14 shrink-0 items-center justify-between border-b border-[#E5E5E5] bg-[#FAFAFA] px-6">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="truncate text-base font-semibold text-[#1a1a1a]">
            {conversation.visitor?.name || `#${conversation.id}`}
          </span>
          {conversation.channel && (
            <span className="shrink-0 rounded border border-[#E5E5E5] bg-[#F5F5F5] px-2 py-0.5 text-[12px] font-medium capitalize text-[#737373]">
              {conversation.channel.channel_type}
            </span>
          )}
          {isClosed && (
            <span className="shrink-0 rounded border border-[#E5E5E5] bg-[#F0F0F0] px-2 py-0.5 text-[12px] font-medium text-[#737373]">
              {t('ws.chat.historyConversation', locale)}
            </span>
          )}
          {isClosed && (
            <span className="max-w-44 truncate text-[12px] text-[#737373]" title={historyEndTime}>
              {historyEndTime}
            </span>
          )}
          <VisitorWebStatusBadge conversation={conversation} socket={socket} />
          {conversation.is_timeout_locked && (
            <span className="shrink-0 rounded border border-[#D6D6D6] bg-[#F0F0F0] px-2 py-0.5 text-[12px] font-medium text-[#555555]">
              {t('ws.chat.timeoutLocked', locale)}
            </span>
          )}
          {isPeerConversation && (
            <span className="shrink-0 rounded border border-[#E5E5E5] bg-[#F5F5F5] px-2 py-0.5 text-[12px] font-medium text-[#737373]">
              {t('ws.chat.peerConversation', locale)}
            </span>
          )}
          {isCollaboratorConversation && (
            <span className="shrink-0 rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[12px] font-medium text-emerald-700">
              {t('ws.chat.collaboratingBadge', locale)}
            </span>
          )}
          {(isPeerConversation || isCollaboratorConversation) && ownerName && (
            <span className="max-w-40 truncate text-[12px] text-[#737373]" title={ownerName}>
              {t('ws.chat.ownerLabel', locale, { name: ownerName })}
            </span>
          )}
          {collaboratorNames.length > 0 && (
            <span
              className="max-w-48 truncate text-[12px] text-[#737373]"
              title={collaboratorNames.join(', ')}
            >
              {t('ws.chat.collaboratorsLabel', locale, {
                names: collaboratorNames.slice(0, 2).join(', '),
              })}
              {collaboratorNames.length > 2 ? ` +${collaboratorNames.length - 2}` : ''}
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {canPinConversation && (
            <button
              onClick={onTogglePinConversation}
              disabled={pinningConversation}
              className={cn(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-60',
                conversation.is_pinned
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                  : 'bg-[#E8E8E8] text-[#666666] hover:bg-[#DDDDDD]',
              )}
              title={pinLabel}
              aria-label={pinLabel}
              type="button"
            >
              {pinningConversation ? (
                <IconLoader2 size={16} stroke={1.5} className="animate-spin" />
              ) : (
                <IconPinned size={16} stroke={1.5} />
              )}
            </button>
          )}
          {canLockConversationTimeout && (
            <button
              onClick={onToggleConversationTimeoutLock}
              disabled={lockingConversationTimeout}
              className={cn(
                'flex h-8 w-8 shrink-0 items-center justify-center rounded-md transition-colors disabled:cursor-not-allowed disabled:opacity-60',
                conversation.is_timeout_locked
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90'
                  : 'bg-[#E8E8E8] text-[#666666] hover:bg-[#DDDDDD]',
              )}
              title={timeoutLockLabel}
              aria-label={timeoutLockLabel}
              type="button"
            >
              {lockingConversationTimeout ? (
                <IconLoader2 size={16} stroke={1.5} className="animate-spin" />
              ) : conversation.is_timeout_locked ? (
                <IconLockOpen size={16} stroke={1.5} />
              ) : (
                <IconLock size={16} stroke={1.5} />
              )}
            </button>
          )}
          {isClosed && (
            <button
              onClick={onStartNewConversation}
              disabled={!canStartNewConversation || startingNewConversation}
              className="flex h-8 items-center gap-1.5 rounded-md bg-[#E8E8E8] px-2.5 text-[12px] font-medium text-[#666666] transition-colors hover:bg-[#DDDDDD] disabled:cursor-not-allowed disabled:opacity-50"
              title={startNewConversationDisabledReason || t('ws.chat.startNewConversation', locale)}
              type="button"
            >
              {startingNewConversation ? (
                <IconLoader2 size={16} stroke={1.5} className="animate-spin" />
              ) : (
                <IconMessagePlus size={16} stroke={1.5} />
              )}
              {t('ws.chat.startNewConversation', locale)}
            </button>
          )}
          {canCreateTicket && (
            <button
              onClick={onCreateTicket}
              className="flex h-8 items-center gap-1.5 rounded-md bg-[#E8E8E8] px-2.5 text-[12px] font-medium text-[#666666] transition-colors hover:bg-[#DDDDDD]"
              title={t('ws.chat.createTicket', locale)}
              type="button"
            >
              <IconTicket size={16} stroke={1.5} />
              {t('ws.chat.createTicket', locale)}
            </button>
          )}
          {!isClosed && canInviteCollaborator && conversation.agent && (
            <button
              onClick={() => setShowInviteModal(true)}
              className="flex h-8 items-center gap-1.5 rounded-md bg-[#E8E8E8] px-2.5 text-[12px] font-medium text-[#666666] transition-colors hover:bg-[#DDDDDD]"
              title={t('ws.chat.collabInviteAction', locale)}
              type="button"
            >
              <IconUserPlus size={16} stroke={1.5} />
              {t('ws.chat.collabInviteAction', locale)}
            </button>
          )}
          {!isClosed && canTransfer && conversation.agent && (
            <button
              onClick={() => setShowTransferModal(true)}
              className="flex h-8 items-center gap-1.5 rounded-md bg-[#E8E8E8] px-2.5 text-[12px] font-medium text-[#666666] transition-colors hover:bg-[#DDDDDD]"
              title={t('ws.chat.transfer', locale)}
              type="button"
            >
              <IconArrowsExchange2 size={16} stroke={1.5} />
              {t('ws.chat.transfer', locale)}
            </button>
          )}
          {canEndConversation && (
            <button
              onClick={() => setShowEndModal(true)}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-[#E8E8E8] text-[#666666] transition-colors hover:bg-[#DDDDDD]"
              title={t('ws.chat.endConversation', locale)}
              type="button"
            >
              <IconX size={18} stroke={1.5} />
            </button>
          )}
        </div>
      </div>

      <ThreadPrimitive.Viewport
        ref={viewportRef}
        onScroll={updateNearBottom}
        className="relative flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain bg-[#FAFAFA] px-6 py-5"
      >
        {showHistoryEntry && (
          <HistoryActionButton
            label={
              historyError
                ? t('ws.chat.historyLoadFailed', locale)
                : t('ws.chat.viewHistory', locale)
            }
            loading={historyLoading}
            onClick={() => void loadHistoryWithAnchor()}
          />
        )}

        {historyLoaded && historyHasMore && !historyLimitReached && (
          <HistoryActionButton
            label={
              historyError
                ? t('ws.chat.historyLoadFailed', locale)
                : t('ws.chat.loadMoreHistory', locale)
            }
            loading={historyLoading}
            onClick={() => void loadHistoryWithAnchor(oldestHistoryId)}
          />
        )}

        {showHistoryDone && (
          <HistoryActionButton
            label={
              historyLimitReached
                ? t('ws.chat.historyLimitReached', locale)
                : t('ws.chat.noMoreHistory', locale)
            }
            disabled
          />
        )}

        {visibleHistoryConversations.map((historyConversation) => (
          <HistoryConversationBlock
            key={historyConversation.id}
            conversation={historyConversation}
            locale={locale}
            visitorAvatarBg={visitorAvatarBg}
            visitorAvatarChar={visitorAvatarChar}
            highlightedMessageId={highlightedMessageId}
            readStatusEnabled={readStatusEnabled}
            currentUserId={currentUserId}
          />
        ))}

        {showCurrentDivider && (
          <ConversationDivider label={t('ws.chat.currentConversation', locale)} />
        )}

        {hasMore ? (
          <button
            className="mx-auto mb-4 flex items-center gap-1 rounded-full px-4 py-1.5 text-[12px] text-[#999999] transition-colors hover:bg-black/[0.04]"
            onClick={onLoadMore}
            disabled={loadingMore}
            type="button"
          >
            {loadingMore ? (
              <IconLoader2 size={14} className="animate-spin" />
            ) : (
              t('ws.chat.loadMore', locale)
            )}
          </button>
        ) : (
          <p className="mb-4 text-center text-[12px] text-[#999999]">{t('ws.chat.noMoreMessages', locale)}</p>
        )}

        {/* Messages */}
        <ThreadPrimitive.Messages>
          {({ message }: { message: MessageState }) => (
            <div
              data-workspace-message-id={message.id}
              className={cn(
                'rounded-2xl transition-colors duration-300',
                highlightedMessageId === Number(message.id) && 'bg-warning/15',
              )}
            >
              <AgentMessageBubble
                message={message}
                socket={socket}
                onComposerInsertRequest={onComposerInsertRequest}
              />
            </div>
          )}
        </ThreadPrimitive.Messages>

        {/* Visitor typing preview */}
        {isTyping && (
          <div className="mb-4 flex gap-2.5">
            <div
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white"
              style={{ backgroundColor: visitorAvatarBg }}
            >
              {visitorAvatarChar}
            </div>
            <div className="flex min-w-0 max-w-[70%] flex-col items-start gap-1">
              {visitorTypingContent ? (
                <>
                  <div className="max-w-full rounded-[18px] border border-dashed border-[#D0D0D0] bg-white px-3.5 py-2.5 text-sm leading-normal break-words break-all whitespace-pre-wrap text-[#1a1a1a] shadow-sm">
                    {visitorTypingContent}
                  </div>
                  <span className="pl-1 text-[11px] italic text-[#999999]">{t('ws.chat.visitorTyping', locale)}</span>
                </>
              ) : (
                <div className="text-[12px] italic text-[#999999]">{t('ws.chat.visitorTyping', locale)}</div>
              )}
            </div>
          </div>
        )}
      </ThreadPrimitive.Viewport>

      {/* ── Composer ── */}
      <AgentComposer
        disabled={isClosed}
        socket={socket}
        insertRequest={composerInsertRequest}
        inputHeight={composerInputHeight}
        onInputHeightCommit={onComposerInputHeightCommit}
        messageSearchOpen={messageSearchOpen}
        onOpenMessageSearch={onOpenMessageSearch}
      />

      {/* ── End conversation modal ── */}
      {showEndModal && (
        <EndConversationModal
          conversation={conversation}
          onClose={() => setShowEndModal(false)}
          socket={socket}
        />
      )}

      {/* ── Transfer conversation modal ── */}
      {canTransfer && (
        <TransferConversationModal
          conversation={conversation}
          open={showTransferModal}
          onClose={() => setShowTransferModal(false)}
          onTransferred={(toName) => {
            setShowTransferModal(false)
            onTransferred(toName)
          }}
        />
      )}

      {canInviteCollaborator && (
        <InviteCollaboratorModal
          conversation={conversation}
          open={showInviteModal}
          onClose={() => setShowInviteModal(false)}
          onInvited={(name) => {
            setShowInviteModal(false)
            onCollaborationInvitationSent(name)
          }}
        />
      )}
    </ThreadPrimitive.Root>
  )
}
