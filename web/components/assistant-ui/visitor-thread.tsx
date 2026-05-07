'use client'

import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ThreadPrimitive, type MessageState } from '@assistant-ui/react'
import {
  useVisitorChatConfig,
  type VisitorMessageMeta,
} from './visitor-chat-runtime'
import { useVisitorChatStore } from '@/context/visitor-chat-store'
import { ChatHeader } from '@/app/components/features/visitor-chat/chat-header'
import { MessageBubble } from '@/app/components/features/visitor-chat/message-bubble'
import { SystemMessage } from '@/app/components/features/visitor-chat/system-message'
import { TypingIndicator } from '@/app/components/features/visitor-chat/typing-indicator'
import { VisitorComposer } from './visitor-composer'
import { IconLoader2, IconMessage, IconArrowDown, IconAlertCircle } from '@tabler/icons-react'
import type { Message, VisitorConversationHistoryItem } from '@/models/conversation'

// ─── Timestamp formatting (reused from original) ────────────────

function formatTimestamp(date: Date, locale: string): string {
  const now = new Date()
  const time = date.toLocaleTimeString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

  const diffDays = Math.floor(
    (now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24),
  )
  if (diffDays === 0 && now.getDate() === date.getDate()) return time
  if (diffDays <= 1 && now.getDate() - date.getDate() === 1) {
    return locale === 'zh' ? `昨天 ${time}` : `Yesterday ${time}`
  }
  if (date.getFullYear() === now.getFullYear()) {
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    return `${m}-${d} ${time}`
  }
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${time}`
}

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

// ─── Reconstruct a Message object from assistant-ui state ───────

function toOriginalMessage(
  message: MessageState,
  meta: VisitorMessageMeta | undefined,
): Message {
  const firstPart = message.content?.[0]
  let content = ''
  if (firstPart) {
    if ('text' in firstPart) content = firstPart.text as string
    else if ('image' in firstPart) content = firstPart.image as string
  }

  return {
    id: Number(message.id) || 0,
    conversation_id: meta?.conversationId ?? 0,
    sender_type: (meta?.senderType || (message.role === 'user' ? 'visitor' : 'agent')) as Message['sender_type'],
    sender_id: meta?.senderId ?? null,
    sender_name: meta?.senderName ?? null,
    sender_avatar: meta?.senderAvatar ?? null,
    content_type: (meta?.contentType || 'text') as Message['content_type'],
    content,
    created_at: message.createdAt?.toISOString() || new Date().toISOString(),
  }
}

function ConversationDivider({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 px-5 py-2 text-xs text-muted-foreground">
      <div className="h-px flex-1 bg-border" />
      <span className="shrink-0">{label}</span>
      <div className="h-px flex-1 bg-border" />
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

function HistoryConversationBlock({
  conversation,
  config,
  locale,
}: {
  conversation: VisitorConversationHistoryItem
  config: ReturnType<typeof useVisitorChatConfig>['config']
  locale: string
}) {
  const startedAt = conversation.started_at || conversation.created_at || conversation.last_message_at
  const dividerLabel = startedAt
    ? `${formatTimestamp(new Date(startedAt), locale)} ${locale === 'zh' ? '历史会话' : 'Past conversation'}`
    : locale === 'zh'
      ? '历史会话'
      : 'Past conversation'

  return (
    <div className="space-y-2">
      <ConversationDivider label={dividerLabel} />
      {conversation.messages_truncated && (
        <SystemMessage
          content={locale === 'zh' ? '仅显示最近 200 条消息' : 'Showing latest 200 messages'}
        />
      )}
      {conversation.messages.map((msg, idx) => {
        const prev = idx > 0 ? conversation.messages[idx - 1] : null
        const next = idx < conversation.messages.length - 1 ? conversation.messages[idx + 1] : null
        const showAvatar = msg.sender_type === 'agent'
          ? config.use_agent_avatar === true
          : shouldShowAvatar(msg, next)

        if (msg.sender_type === 'system') {
          return <SystemMessage key={msg.id} content={msg.content} />
        }

        return (
          <div key={msg.id}>
            {shouldShowTimestamp(msg, prev) && (
              <div className="py-2 text-center text-[10px] text-muted-foreground">
                {formatTimestamp(new Date(msg.created_at), locale)}
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
}

export function VisitorThread({ offlineTitle, offlineMessage }: VisitorThreadProps) {
  const {
    channel,
    config,
    locale,
    isMobile,
    ended,
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
    onRestartConversation,
  } = useVisitorChatConfig()
  const agentTyping = useVisitorChatStore((s) => s.agentTyping)
  const msgCount = useVisitorChatStore((s) => s.messages.length)
  const messages = useVisitorChatStore((s) => s.messages)
  const activeAgent = useVisitorChatStore((s) => s.activeAgent)
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const pendingScrollDeltaRef = useRef<number | null>(null)

  const welcomeMessage =
    locale === 'zh' ? '您好，有什么可以帮您？' : 'Hi, how can we help?'
  const isOffline = Boolean(offlineMessage)
  const oldestHistoryId = historyConversations[0]?.id
  const showCurrentDivider = historyLoaded && !isOffline && historyConversations.length > 0
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
    <ThreadPrimitive.Root className="flex h-full flex-col">
      <ChatHeader channel={channel} isMobile={isMobile} />

      <ThreadPrimitive.Viewport
        ref={viewportRef}
        className="relative flex flex-1 flex-col gap-2 overflow-y-auto py-3"
        style={{
          backgroundColor:
            config.message_area_bg_color || 'var(--color-background)',
        }}
      >
        {showHistoryEntry && (
          <HistoryActionButton
            label={
              historyError
                ? locale === 'zh'
                  ? '加载失败，点击重试'
                  : 'Failed to load, tap to retry'
                : locale === 'zh'
                  ? '查看历史会话'
                  : 'View previous conversations'
            }
            loading={historyLoading}
            onClick={() => void loadHistoryWithAnchor()}
          />
        )}

        {historyLoaded && historyHasMore && !historyLimitReached && (
          <HistoryActionButton
            label={
              historyError
                ? locale === 'zh'
                  ? '加载失败，点击重试'
                  : 'Failed to load, tap to retry'
                : locale === 'zh'
                  ? '更多历史会话'
                  : 'Load more conversations'
            }
            loading={historyLoading}
            onClick={() => void loadHistoryWithAnchor(oldestHistoryId)}
          />
        )}

        {showHistoryDone && (
          <HistoryActionButton
            label={
              historyLimitReached
                ? locale === 'zh'
                  ? '已加载较多历史，建议刷新或联系客服查阅更早记录'
                  : 'You have loaded a lot of history, please refresh or contact support for older records'
                : locale === 'zh'
                  ? '已无更多历史会话'
                  : 'No more conversations'
            }
            disabled
          />
        )}

        {historyConversations.map((conversation) => (
          <HistoryConversationBlock
            key={conversation.id}
            conversation={conversation}
            config={config}
            locale={locale}
          />
        ))}

        {showCurrentDivider && (
          <ConversationDivider label={locale === 'zh' ? '当前会话' : 'Current conversation'} />
        )}

        {isOffline ? (
          <div className="flex flex-1 items-center justify-center p-6">
            <div className="w-full max-w-[520px] rounded-xl border border-border bg-card p-6 shadow-sm">
              <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-foreground">
                <IconAlertCircle size={18} className="text-amber-600" />
                {offlineTitle || (locale === 'zh' ? '当前客服不在线' : 'Support is offline')}
              </div>
              <div
                className="prose prose-sm max-w-none text-sm leading-6 text-muted-foreground"
                dangerouslySetInnerHTML={{ __html: offlineMessage || '' }}
              />
            </div>
          </div>
        ) : (
          <>
            {/* ── Empty state ── */}
            {msgCount === 0 && !loadingMore && (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8">
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-muted">
                  <IconMessage size={28} className="text-muted-foreground" />
                </div>
                <p className="max-w-xs text-center text-sm text-muted-foreground">
                  {welcomeMessage}
                </p>
              </div>
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
                ) : locale === 'zh' ? (
                  '加载更多'
                ) : (
                  'Load more'
                )}
              </button>
            )}

            {/* ── Messages (via assistant-ui) ── */}
            {msgCount > 0 && (
              <ThreadPrimitive.Messages>
                {({ message }: { message: MessageState }) => {
                  const meta = message.metadata?.custom as VisitorMessageMeta | undefined
                  const original = toOriginalMessage(message, meta)

                  return (
                    <div>
                      {meta?.showTimestamp && message.createdAt && (
                        <div className="py-2 text-center text-[10px] text-muted-foreground">
                          {formatTimestamp(message.createdAt, locale)}
                        </div>
                      )}

                      {message.role === 'system' ? (
                        <SystemMessage content={original.content} />
                      ) : (
                        <MessageBubble
                          message={original}
                          config={config}
                          showAvatar={meta?.showAvatar ?? true}
                          showName={meta?.showName ?? true}
                          locale={locale}
                          messageStatus={meta?.messageStatus}
                          showTime={false}
                        />
                      )}
                    </div>
                  )
                }}
              </ThreadPrimitive.Messages>
            )}

            {/* ── Typing indicator ── */}
            {agentTyping && (
              <TypingIndicator
                agentBubbleBg={config.agent_bubble_bg_color || undefined}
                agentBubbleTextColor={config.agent_bubble_text_color || undefined}
                agentBubbleRadius={config.agent_bubble_radius}
                agentBubbleBorder={config.agent_bubble_border_color || undefined}
                showAvatar={config.use_agent_avatar === true}
                agentAvatar={typingAgent.avatar}
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

      {!isOffline && (
        ended ? (
          <ConversationEndedPanel
            locale={locale}
            onRestartConversation={onRestartConversation}
          />
        ) : (
          <VisitorComposer
            disabled={false}
            isMobile={isMobile}
          />
        )
      )}
    </ThreadPrimitive.Root>
  )
}

function ConversationEndedPanel({
  locale,
  onRestartConversation,
}: {
  locale: string
  onRestartConversation: () => Promise<void>
}) {
  const [restarting, setRestarting] = useState(false)

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
          {locale === 'zh' ? '会话已结束' : 'Conversation ended'}
        </span>
        <button
          type="button"
          onClick={handleRestart}
          disabled={restarting}
          className="shrink-0 rounded-full bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {restarting
            ? locale === 'zh'
              ? '重启中...'
              : 'Restarting...'
            : locale === 'zh'
              ? '重启会话'
              : 'Restart'}
        </button>
      </div>
    </div>
  )
}
