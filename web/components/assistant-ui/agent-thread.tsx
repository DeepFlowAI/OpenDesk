'use client'

import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ThreadPrimitive, type MessageState } from '@assistant-ui/react'
import {
  useAgentChatConfig,
  type AgentMessageMeta,
} from './agent-chat-runtime'
import { AgentComposer } from './agent-composer'
import { IconArrowsExchange2, IconTicket, IconX, IconLoader2 } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useLocaleStore } from '@/context/locale-store'
import { useAuthStore } from '@/context/auth-store'
import { t } from '@/utils/i18n'
import { EndConversationModal } from '@/app/components/features/chat/end-conversation-modal'
import { TransferConversationModal } from '@/app/components/features/chat/transfer-conversation-modal'
import { MessageAttachment } from '@/app/components/features/chat/message-attachment'
import type { Message, WorkspaceConversationHistoryItem } from '@/models/conversation'
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

// ─── Agent-side message bubble ───────────────────────────────────

function AgentMessageBubble({ message }: { message: MessageState }) {
  const { conversation, imageMessages } = useAgentChatConfig()
  const meta = message.metadata?.custom as AgentMessageMeta | undefined
  const isOwn = meta?.isOwn ?? false
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

  if (isSystem) {
    return (
      <div className="mb-4 flex justify-center py-1">
        <span className="text-center text-[12px] leading-normal text-[#999999]">{content}</span>
      </div>
    )
  }

  // 2.1 pen: visitor left (#F0F0F0 + border), agent (own) right (#DBEAFE)
  return (
    <div className={cn('mb-4 flex gap-2.5', isOwn ? 'flex-row-reverse' : 'flex-row')}>
      {isOwn ? (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#D6E6F9] text-sm font-medium text-[#4A80B5]">
          {(meta?.senderName || 'A').charAt(0)}
        </div>
      ) : (
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white"
          style={{ backgroundColor: visitorAvatarBg }}
        >
          {visitorAvatarChar}
        </div>
      )}
      <div className={cn('flex max-w-[70%] flex-col', isOwn ? 'items-end' : 'items-start')}>
        {attachmentContentType ? (
          <MessageAttachment
            conversationId={meta?.conversationId ?? conversation.id}
            contentType={attachmentContentType}
            content={content}
            imageGallery={attachmentContentType === 'image' ? imageMessages : undefined}
            currentImageId={attachmentContentType === 'image' ? message.id : undefined}
          />
        ) : (
          <div
            className={cn(
              'rounded-[18px] px-3.5 py-2.5 text-sm leading-normal whitespace-pre-wrap text-[#1a1a1a]',
              isOwn ? 'bg-[#DBEAFE]' : 'border border-[#E0E0E0] bg-[#F0F0F0]',
            )}
          >
            {content}
          </div>
        )}
        <span className={cn('mt-1 text-[11px] text-[#999999]', isOwn && 'text-right')}>
          {message.createdAt ? formatMessageTime(message.createdAt.toISOString()) : ''}
        </span>
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
  visitorAvatarBg,
  visitorAvatarChar,
  imageMessages,
}: {
  message: Message
  visitorAvatarBg: string
  visitorAvatarChar: string
  imageMessages: { id: string; content: string }[]
}) {
  const isAgent = message.sender_type === 'agent'
  const isSystem = message.sender_type === 'system'
  const attachmentContentType =
    message.content_type === 'image' ? 'image' : message.content_type === 'file' ? 'file' : null

  if (isSystem) {
    return (
      <div className="mb-4 flex justify-center py-1">
        <span className="text-center text-[12px] leading-normal text-[#999999]">{message.content}</span>
      </div>
    )
  }

  return (
    <div className={cn('mb-4 flex gap-2.5 opacity-90', isAgent ? 'flex-row-reverse' : 'flex-row')}>
      {isAgent ? (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#E8E8E8] text-sm font-medium text-[#737373]">
          {(message.sender_name || 'A').charAt(0)}
        </div>
      ) : (
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-medium text-white"
          style={{ backgroundColor: visitorAvatarBg }}
        >
          {visitorAvatarChar}
        </div>
      )}
      <div className={cn('flex max-w-[70%] flex-col', isAgent ? 'items-end' : 'items-start')}>
        {attachmentContentType ? (
          <MessageAttachment
            conversationId={message.conversation_id}
            contentType={attachmentContentType}
            content={message.content}
            imageGallery={attachmentContentType === 'image' ? imageMessages : undefined}
            currentImageId={attachmentContentType === 'image' ? String(message.id) : undefined}
          />
        ) : (
          <div
            className={cn(
              'rounded-[18px] px-3.5 py-2.5 text-sm leading-normal whitespace-pre-wrap text-[#1a1a1a]',
              isAgent ? 'bg-[#E8E8E8]' : 'border border-[#E0E0E0] bg-white',
            )}
          >
            {message.content}
          </div>
        )}
        <span className={cn('mt-1 text-[11px] text-[#999999]', isAgent && 'text-right')}>
          {formatMessageTime(message.created_at)}
        </span>
      </div>
    </div>
  )
}

function HistoryConversationBlock({
  conversation,
  locale,
  visitorAvatarBg,
  visitorAvatarChar,
}: {
  conversation: WorkspaceConversationHistoryItem
  locale: string
  visitorAvatarBg: string
  visitorAvatarChar: string
}) {
  const imageMessages = useMemo(
    () =>
      conversation.messages
        .filter((msg) => msg.content_type === 'image')
        .map((msg) => ({ id: String(msg.id), content: msg.content })),
    [conversation.messages],
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
      {conversation.messages.map((message) => (
        <AgentHistoryMessageBubble
          key={message.id}
          message={message}
          visitorAvatarBg={visitorAvatarBg}
          visitorAvatarChar={visitorAvatarChar}
          imageMessages={imageMessages}
        />
      ))}
    </div>
  )
}

// ─── Main Thread ─────────────────────────────────────────────────

type AgentThreadProps = {
  socket: Socket | null
}

export function AgentThread({ socket }: AgentThreadProps) {
  const {
    conversation,
    locale: cfgLocale,
    isClosed,
    isTyping,
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
    onTransferred,
  } = useAgentChatConfig()
  const { locale } = useLocaleStore()
  const userId = useAuthStore((s) => s.user?.id)
  const userRoles = useAuthStore((s) => s.user?.roles ?? [])
  // Mirror the backend's transfer authorization: only the conversation's
  // current owner or an admin may initiate a transfer. Hiding the button for
  // unauthorized users avoids 403s and the modal's listing endpoint also
  // refuses to leak the candidate list to them.
  const isAdmin = userRoles.includes('admin')
  const isOwner = userId != null && conversation.agent?.id === userId
  const canTransfer = isAdmin || isOwner
  const [showEndModal, setShowEndModal] = useState(false)
  const [showTransferModal, setShowTransferModal] = useState(false)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const pendingScrollDeltaRef = useRef<number | null>(null)
  const visitorAvatarBg = conversation.visitor?.avatar_color || '#4A8C5C'
  const visitorAvatarChar = (conversation.visitor?.name || '访').charAt(0)
  const oldestHistoryId = historyConversations[0]?.id
  const showHistoryEntry = historyAvailable && !historyLoaded
  const showCurrentDivider = historyLoaded && historyConversations.length > 0
  const showHistoryDone =
    historyLoaded && historyConversations.length > 0 && (!historyHasMore || historyLimitReached)

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

  return (
    <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col bg-white">
      {/* 会话头部 — 2.1 pen: #FAFAFA, 56px, px 24 */}
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-[#E5E5E5] bg-[#FAFAFA] px-6">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="truncate text-base font-semibold text-[#1a1a1a]">
            {conversation.visitor?.name || `#${conversation.id}`}
          </span>
          {conversation.channel && (
            <span className="shrink-0 rounded border border-[#E5E5E5] bg-[#F5F5F5] px-2 py-0.5 text-[12px] font-medium capitalize text-[#737373]">
              {conversation.channel.channel_type}
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            onClick={onCreateTicket}
            className="flex h-8 items-center gap-1.5 rounded-md bg-[#E8E8E8] px-2.5 text-[12px] font-medium text-[#666666] transition-colors hover:bg-[#DDDDDD]"
            title={t('ws.chat.createTicket', locale)}
            type="button"
          >
            <IconTicket size={16} stroke={1.5} />
            {t('ws.chat.createTicket', locale)}
          </button>
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
          {!isClosed && (
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
        className="relative flex min-h-0 flex-1 flex-col overflow-y-auto bg-[#FAFAFA] px-6 py-5"
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

        {historyConversations.map((historyConversation) => (
          <HistoryConversationBlock
            key={historyConversation.id}
            conversation={historyConversation}
            locale={locale}
            visitorAvatarBg={visitorAvatarBg}
            visitorAvatarChar={visitorAvatarChar}
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
            <AgentMessageBubble message={message} />
          )}
        </ThreadPrimitive.Messages>

        {/* Visitor typing indicator */}
        {isTyping && (
          <div className="mb-2 text-[12px] italic text-[#999999]">{t('ws.chat.visitorTyping', locale)}</div>
        )}
      </ThreadPrimitive.Viewport>

      {/* ── Composer ── */}
      <AgentComposer disabled={isClosed} socket={socket} />

      {/* ── End conversation modal ── */}
      {showEndModal && (
        <EndConversationModal
          conversation={conversation}
          onClose={() => setShowEndModal(false)}
          socket={socket}
        />
      )}

      {/* ── Transfer conversation modal ── */}
      <TransferConversationModal
        conversation={conversation}
        open={showTransferModal}
        onClose={() => setShowTransferModal(false)}
        onTransferred={(toName) => {
          setShowTransferModal(false)
          onTransferred(toName)
        }}
      />
    </ThreadPrimitive.Root>
  )
}
