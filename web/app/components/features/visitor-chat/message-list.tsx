'use client'

import { useRef, useEffect, useCallback, useState } from 'react'
import type { Message } from '@/models/conversation'
import type { ChannelConfig } from '@/models/channel'
import { MessageBubble } from './message-bubble'
import { SystemMessage } from './system-message'
import { WelcomeMessage } from './welcome-message'
import { TypingIndicator } from './typing-indicator'
import { IconLoader2 } from '@tabler/icons-react'

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
      && msg.content_type !== 'welcome',
  )
  const hasWelcomeMessage = messages.some((msg) => msg.content_type === 'welcome')

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
            showAvatar={config.use_agent_avatar === true}
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
              showAvatar={config.use_agent_avatar === true}
            />
          )}
        </div>
      )}

      {messages.map((msg, idx) => {
        const prev = idx > 0 ? messages[idx - 1] : null
        const next = idx < messages.length - 1 ? messages[idx + 1] : null
        const showTs = shouldShowTimestamp(msg, prev)

        if (msg.content_type === 'welcome') {
          return (
            <div key={msg.id}>
              {showTs && (
                <div className="py-2 text-center text-[10px] text-muted-foreground">
                  {formatTimestamp(msg.created_at, locale)}
                </div>
              )}
              <WelcomeMessage
                content={msg.content}
                config={config}
                showAvatar={config.use_agent_avatar === true}
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
              <SystemMessage content={msg.content} />
            </div>
          )
        }

        const showAvatar = msg.sender_type === 'agent'
          ? config.use_agent_avatar === true
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
          showAvatar={config.use_agent_avatar === true}
          agentAvatar={latestAgentMessage?.sender_avatar}
          agentName={latestAgentMessage?.sender_name}
          locale={locale}
        />
      )}

      <div ref={bottomRef} />
    </div>
  )
}
