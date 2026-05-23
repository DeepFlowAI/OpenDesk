'use client'

import type { Message } from '@/models/conversation'
import type { ChannelConfig } from '@/models/channel'
import { useMemo } from 'react'
import { MessageAttachment } from '@/app/components/features/chat/message-attachment'
import { useVisitorChatConfig } from '@/components/assistant-ui/visitor-chat-runtime'

const DEFAULT_AGENT_AVATAR_SRC = '/default-avatar.jpg'

function toCssBorderRadius(radius: [number, number, number, number]): string {
  const [topLeft, topRight, bottomLeft, bottomRight] = radius
  return `${topLeft}px ${topRight}px ${bottomRight}px ${bottomLeft}px`
}

type MessageBubbleProps = {
  message: Message
  config: ChannelConfig
  showAvatar: boolean
  showName: boolean
  locale: string
  messageStatus?: string
  showTime?: boolean
}

function formatTime(dateStr: string, locale: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  const time = date.toLocaleTimeString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })

  if (diffDays === 0 && now.getDate() === date.getDate()) return time
  if (diffDays <= 1 && now.getDate() - date.getDate() === 1) {
    return locale === 'zh' ? `昨天 ${time}` : `Yesterday ${time}`
  }
  if (date.getFullYear() === now.getFullYear()) {
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${month}-${day} ${time}`
  }
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day} ${time}`
}

function statusLabel(status: string | undefined, locale: string): string | null {
  if (!status) return null
  if (status === 'sending') return locale === 'zh' ? '发送中' : 'Sending'
  if (status === 'delivered') return locale === 'zh' ? '已送达' : 'Delivered'
  if (status === 'read') return locale === 'zh' ? '已读' : 'Read'
  return null
}

export function MessageBubble({
  message,
  config,
  showAvatar,
  showName,
  locale,
  messageStatus,
  showTime = true,
}: MessageBubbleProps) {
  const isUser = message.sender_type === 'visitor'
  const isAgent = message.sender_type === 'agent'
  const visitorChat = useVisitorChatConfig()
  const statusText = isUser ? statusLabel(messageStatus || message.status, locale) : null

  const bubbleStyle = useMemo(() => {
    if (isUser) {
      const radius = config.user_bubble_radius || [10, 10, 10, 0]
      return {
        backgroundColor: config.user_bubble_bg_color || 'var(--color-primary)',
        color: config.user_bubble_text_color || 'var(--color-primary-foreground)',
        borderRadius: toCssBorderRadius(radius),
        border: config.user_bubble_border_color ? `1px solid ${config.user_bubble_border_color}` : undefined,
      }
    }
    const radius = config.agent_bubble_radius || [10, 10, 0, 10]
    return {
      backgroundColor: config.agent_bubble_bg_color || 'var(--color-secondary)',
      color: config.agent_bubble_text_color || 'var(--color-foreground)',
      borderRadius: toCssBorderRadius(radius),
      border: config.agent_bubble_border_color ? `1px solid ${config.agent_bubble_border_color}` : undefined,
    }
  }, [isUser, config])

  const attachmentContentType =
    message.content_type === 'image' ? 'image' : message.content_type === 'file' ? 'file' : null

  return (
    <div className={`flex ${isUser ? 'flex-row-reverse' : 'flex-row'} items-end gap-2 px-5`}>
      {/* Avatar */}
      {showAvatar && !isUser && (
        <img
          src={message.sender_avatar || DEFAULT_AGENT_AVATAR_SRC}
          alt={message.sender_name || ''}
          className="h-9 w-9 shrink-0 rounded-full object-cover"
        />
      )}

      {/* Bubble */}
      <div className={`flex max-w-[75%] flex-col ${isUser ? 'items-end' : 'items-start'}`}>
        {showName && isAgent && message.sender_name && (
          <span className="mb-1 text-xs font-medium text-muted-foreground">
            {message.sender_name}
          </span>
        )}

        {attachmentContentType ? (
          <MessageAttachment
            conversationId={message.conversation_id}
            conversationPublicId={message.conversation_public_id}
            visitorSessionToken={visitorChat.visitorSessionToken}
            contentType={attachmentContentType}
            content={message.content}
          />
        ) : (
          <div className="flex min-h-[42px] items-center whitespace-pre-wrap break-words px-3 py-2 text-sm" style={bubbleStyle}>
            {message.content}
          </div>
        )}

        {(showTime || statusText) && (
          <div className={`mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground ${isUser ? 'flex-row-reverse' : ''}`}>
            {showTime && <span>{formatTime(message.created_at, locale)}</span>}
            {statusText && (
              <span className={messageStatus === 'read' || message.status === 'read' ? 'text-primary' : ''}>
                {statusText}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
