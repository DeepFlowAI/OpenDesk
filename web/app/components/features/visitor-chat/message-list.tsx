'use client'

import { useRef, useEffect, useCallback, useState } from 'react'
import type { Message } from '@/models/conversation'
import type { ChannelConfig } from '@/models/channel'
import { MessageBubble } from './message-bubble'
import { SystemMessage } from './system-message'
import { resolveVisitorSystemEventContent } from '@/lib/workspace-agent-display'
import {
  HumanHandoffEventMessage,
  isOpenAgentHandoffEventMessage,
  resolveHandoffEventType,
} from './human-handoff-event-message'
import {
  OpenAgentWelcomeMessage,
  WelcomeMessage,
} from './welcome-message'
import { TypingIndicator } from './typing-indicator'
import { IconLoader2 } from '@tabler/icons-react'
import {
  getAgentAvatarUrl,
  getOpenAgentAvatarUrl,
  shouldShowAgentAvatar,
  shouldShowAssistantAvatar,
} from './avatar'
import { isLeaveMessagePromptMessage } from '@/lib/offline-message-event'
import { getOpenAgentWelcomeBlocksFromMetadata } from '@/lib/open-agent-welcome-message'
import { isWelcomeLikeContentType } from '@/lib/welcome-message-content-type'

type MessageListProps = {
  messages: Message[]
  config: ChannelConfig
  agentTyping: boolean
  hasMore: boolean
  loading: boolean
  locale: string
  welcomeMessage: string
  onLoadMore: () => void
}

function shouldShowTimestamp(current: Message, prev: Message | null): boolean {
  if (!prev) return true
  const currentTime = new Date(current.created_at).getTime()
  const prevTime = new Date(prev.created_at).getTime()
  return currentTime - prevTime > 5 * 60 * 1000
}

function shouldShowAvatar(current: Message, next: Message | null): boolean {
  if (!next) return true
  return next.sender_type !== current.sender_type
}

function shouldShowName(current: Message, prev: Message | null): boolean {
  if (!prev) return true
  return prev.sender_type !== current.sender_type || prev.sender_id !== current.sender_id
}

function formatTimestamp(dateStr: string, locale: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const time = date.toLocaleTimeString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })

  const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24))
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

function VisitorWelcomeBubble({
  message,
  config,
}: {
  message: Message
  config: ChannelConfig
}) {
  const openAgentWelcomeBlocks = getOpenAgentWelcomeBlocksFromMetadata(message.metadata)

  if (openAgentWelcomeBlocks.length > 0) {
    return (
      <OpenAgentWelcomeMessage
        blocks={openAgentWelcomeBlocks}
        config={config}
        showAvatar={shouldShowAssistantAvatar('bot', config)}
        avatarSrc={getOpenAgentAvatarUrl(config)}
      />
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

export function MessageList({
  messages,
  config,
  agentTyping,
  hasMore,
  loading,
  locale,
  welcomeMessage,
  onLoadMore,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const latestAgentMessage = [...messages].reverse().find((msg) => msg.sender_type === 'agent')
  const hasConversationMessages = messages.some(
    (msg) =>
      msg.sender_type !== 'system'
      && msg.content_type !== 'system'
      && !isWelcomeLikeContentType(msg.content_type),
  )
  const hasWelcomeMessage = messages.some((msg) => isWelcomeLikeContentType(msg.content_type))

  useEffect(() => {
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, agentTyping, autoScroll])

  const handleScroll = useCallback(() => {
    const el = listRef.current
    if (!el) return
    const isNearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
    setAutoScroll(isNearBottom)
  }, [])

  if (messages.length === 0 && !loading) {
    return (
      <div
        className="flex flex-1 flex-col py-3"
        style={{ backgroundColor: config.message_area_bg_color || 'var(--color-background)' }}
      >
        {welcomeMessage && (
          <WelcomeMessage
            content={welcomeMessage}
            config={config}
            showAvatar={shouldShowAgentAvatar(null, config)}
            avatarSrc={getAgentAvatarUrl(null, config)}
          />
        )}
      </div>
    )
  }

  return (
    <div
      ref={listRef}
      className="flex flex-1 flex-col gap-2 overflow-y-auto py-3"
      style={{ backgroundColor: config.message_area_bg_color || 'var(--color-background)' }}
      onScroll={handleScroll}
    >
      {hasMore && (
        <button
          className="mx-auto mb-2 flex items-center gap-1 rounded-full px-4 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted"
          onClick={onLoadMore}
          disabled={loading}
        >
          {loading ? (
            <IconLoader2 size={14} className="animate-spin" />
          ) : (
            locale === 'zh' ? '加载更多' : 'Load more'
          )}
        </button>
      )}

      {!hasConversationMessages && !hasWelcomeMessage && !loading && (
        <div className="py-1">
          {welcomeMessage && (
            <WelcomeMessage
              content={welcomeMessage}
              config={config}
              showAvatar={shouldShowAgentAvatar(null, config)}
              avatarSrc={getAgentAvatarUrl(null, config)}
            />
          )}
        </div>
      )}

      {messages.map((msg, idx) => {
        const prev = idx > 0 ? messages[idx - 1] : null
        const next = idx < messages.length - 1 ? messages[idx + 1] : null
        const showTs = shouldShowTimestamp(msg, prev)

        if (isWelcomeLikeContentType(msg.content_type)) {
          return (
            <div key={msg.id}>
              {showTs && (
                <div className="py-2 text-center text-[10px] text-muted-foreground">
                  {formatTimestamp(msg.created_at, locale)}
                </div>
              )}
              <VisitorWelcomeBubble
                message={msg}
                config={config}
              />
            </div>
          )
        }

        if (msg.sender_type === 'system' || msg.content_type === 'system') {
          return (
            <div key={msg.id}>
              {showTs && (
                <div className="py-2 text-center text-[10px] text-muted-foreground">
                  {formatTimestamp(msg.created_at, locale)}
                </div>
              )}
              {isLeaveMessagePromptMessage(msg) ? (
                <WelcomeMessage
                  content={msg.content}
                  config={config}
                  showAvatar={shouldShowAgentAvatar(null, config)}
                  avatarSrc={getAgentAvatarUrl(null, config)}
                />
              ) : isOpenAgentHandoffEventMessage(msg) ? (
                <HumanHandoffEventMessage
                  content={msg.content}
                  config={config}
                  locale={locale}
                  handoffEventType={resolveHandoffEventType(msg.metadata)}
                />
              ) : (
                <SystemMessage content={resolveVisitorSystemEventContent(msg.content, msg.metadata, locale)} />
              )}
            </div>
          )
        }

        const showAvatar = msg.sender_type === 'agent' || msg.sender_type === 'bot'
          ? shouldShowAssistantAvatar(msg, config)
          : shouldShowAvatar(msg, next)

        return (
          <div key={msg.id}>
            {showTs && (
              <div className="py-2 text-center text-[10px] text-muted-foreground">
                {formatTimestamp(msg.created_at, locale)}
              </div>
            )}
            <MessageBubble
              message={msg}
              config={config}
              showAvatar={showAvatar}
              showName={shouldShowName(msg, prev)}
              locale={locale}
            />
          </div>
        )
      })}

      {agentTyping && (
        <TypingIndicator
          agentBubbleBg={config.agent_bubble_bg_color || undefined}
          agentBubbleTextColor={config.agent_bubble_text_color || undefined}
          agentBubbleRadius={config.agent_bubble_radius}
          agentBubbleBorder={config.agent_bubble_border_color || undefined}
          showAvatar={shouldShowAgentAvatar(latestAgentMessage?.sender_avatar, config)}
          agentAvatar={getAgentAvatarUrl(latestAgentMessage?.sender_avatar, config)}
          agentName={latestAgentMessage?.sender_name}
          locale={locale}
        />
      )}

      <div ref={bottomRef} />
    </div>
  )
}
