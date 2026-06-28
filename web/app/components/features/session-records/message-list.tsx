'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { IconLoader2 } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useSessionRecordMessages } from '@/service/use-session-records'
import { MessageAttachment } from '@/app/components/features/chat/message-attachment'
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
import {
  OpenAgentWelcomeMessage,
  WelcomeMessage,
} from '@/app/components/features/visitor-chat/welcome-message'
import { MarkdownText, markdownTextRootClass } from '@/components/assistant-ui/markdown-text'
import type { SessionRecordMessage } from '@/models/session-record'
import { resolveOpenAgentHandoffEventLabel } from '@/lib/open-agent-handoff-event'
import { isLeaveMessagePromptMessage } from '@/lib/offline-message-event'
import { getOpenAgentWelcomeBlocksFromMetadata } from '@/lib/open-agent-welcome-message'
import { isWelcomeLikeContentType } from '@/lib/welcome-message-content-type'
import {
  getWorkspaceAgentAvatarLetter,
  sanitizeWorkspaceAgentEventContent,
  resolveWorkspaceSystemEventContent,
} from '@/lib/workspace-agent-display'

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

function formatFullTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleString('sv-SE', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).replace('T', ' ')
}

function EventTimestamp({ createdAt }: { createdAt: string }) {
  return (
    <div
      className="mt-0.5 cursor-default text-center text-[10px] text-muted-foreground"
      title={formatFullTime(createdAt)}
    >
      {formatTime(createdAt)}
    </div>
  )
}

type Props = {
  recordId: number
  onSatisfactionEventClick?: () => void
}

export function MessageList({ recordId, onSatisfactionEventClick }: Props) {
  const { locale } = useLocaleStore()
  const [allMessages, setAllMessages] = useState<SessionRecordMessage[]>([])
  const [afterId, setAfterId] = useState<number | undefined>(undefined)
  const [hasMore, setHasMore] = useState(true)
  const [loadCount, setLoadCount] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  const { data, isLoading, isError } = useSessionRecordMessages(recordId, afterId)

  useEffect(() => {
    setAllMessages([])
    setAfterId(undefined)
    setHasMore(true)
    setLoadCount(0)
  }, [recordId])

  useEffect(() => {
    if (data && data.items.length > 0) {
      setAllMessages((prev) => {
        const existingIds = new Set(prev.map((m) => m.id))
        const newItems = data.items.filter((m) => !existingIds.has(m.id))
        return [...prev, ...newItems]
      })
      setHasMore(data.has_more)
    } else if (data && data.items.length === 0) {
      setHasMore(false)
    }
  }, [data])

  const handleLoadMore = useCallback(() => {
    if (allMessages.length > 0) {
      setAfterId(allMessages[allMessages.length - 1].id)
      setLoadCount((c) => c + 1)
    }
  }, [allMessages])

  if (isError) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-destructive">
        {t('ws.records.sessions.detail.loadFailed', locale)}
      </div>
    )
  }

  return (
    <div ref={containerRef} className="flex h-full flex-col overflow-y-auto px-4 py-3">
      {isLoading && allMessages.length === 0 ? (
        <div className="flex flex-1 items-center justify-center">
          <IconLoader2 size={24} className="animate-spin text-muted-foreground" />
        </div>
      ) : (
        <>
          {allMessages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
              locale={locale}
              onSatisfactionEventClick={onSatisfactionEventClick}
            />
          ))}

          {/* Load more / all loaded */}
          <div className="mt-2 mb-1 text-center">
            {hasMore ? (
              <button
                onClick={handleLoadMore}
                disabled={isLoading}
                className="inline-flex items-center gap-1 rounded-full px-4 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-muted"
              >
                {isLoading ? (
                  <IconLoader2 size={14} className="animate-spin" />
                ) : (
                  t('ws.records.sessions.detail.loadMore', locale)
                )}
              </button>
            ) : allMessages.length > 0 ? (
              <span className="text-xs text-muted-foreground">
                {t('ws.records.sessions.detail.allLoaded', locale)}
              </span>
            ) : null}
          </div>
        </>
      )}
    </div>
  )
}

function MessageBubble({
  message,
  locale,
  onSatisfactionEventClick,
}: {
  message: SessionRecordMessage
  locale: string
  onSatisfactionEventClick?: () => void
}) {
  const isSystem = message.sender_type === 'system' || message.content_type === 'system'
  const isAgent = message.sender_type === 'agent'
  const isBot = message.sender_type === 'bot'
  const isAssistant = isAgent || isBot
  const isOwn = isAssistant
  const textBlocks = isBot ? getOpenAgentTextBlocks(message.metadata) : []
  const thinkingBlocks = isBot ? getOpenAgentThinkingBlocks(message.metadata) : []
  const visibleToolBlocks = isBot ? getVisibleOpenAgentToolBlocks(message.metadata) : []
  const hasOpenAgentTrace =
    isBot && (textBlocks.length > 0 || thinkingBlocks.length > 0 || visibleToolBlocks.length > 0)
  const hasMessageText = message.content.trim().length > 0

  if (isWelcomeLikeContentType(message.content_type) || isLeaveMessagePromptMessage(message)) {
    const openAgentWelcomeBlocks = getOpenAgentWelcomeBlocksFromMetadata(message.metadata)
    return (
      <div className="my-3">
        {openAgentWelcomeBlocks.length > 0 ? (
          <OpenAgentWelcomeMessage blocks={openAgentWelcomeBlocks} align="end" />
        ) : (
          <WelcomeMessage content={message.content} align="end" />
        )}
      </div>
    )
  }

  if (message.content_type === 'satisfaction_event') {
    const submitted = message.event_type === 'feedback_submitted'
    return (
      <div className="my-3 text-center">
        <button
          type="button"
          onClick={onSatisfactionEventClick}
          className={cn(
            'rounded-full px-3 py-1.5 text-xs font-medium transition-opacity hover:opacity-80',
            submitted ? 'bg-[#F0FDF4] text-[#16A34A]' : 'bg-[#EFF6FF] text-[#3B82F6]',
          )}
        >
          {sanitizeWorkspaceAgentEventContent(message.content, locale)}
        </button>
        <EventTimestamp createdAt={message.created_at} />
      </div>
    )
  }

  if (isSystem) {
    const handoffEventLabel = resolveOpenAgentHandoffEventLabel(message.metadata, locale)
    const systemContent = handoffEventLabel || message.content
    return (
      <div className="my-3 text-center">
        <span className="rounded-full bg-secondary px-3 py-1 text-xs text-muted-foreground">
          {resolveWorkspaceSystemEventContent(systemContent, message.metadata, locale)}
        </span>
        <EventTimestamp createdAt={message.created_at} />
      </div>
    )
  }

  if (isBot && !hasOpenAgentTrace && !hasMessageText) return null

  const avatarLetter = isAssistant
    ? getWorkspaceAgentAvatarLetter(isBot, message.sender_name)
    : (message.sender_name || 'V').charAt(0).toUpperCase()
  const senderLabel = isBot
    ? (message.sender_name || '智能助手')
    : isAgent
      ? null
      : (message.sender_name || 'V')

  return (
    <div className={cn('mb-3 flex gap-2', isOwn ? 'flex-row-reverse' : 'flex-row')}>
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-medium text-white',
          isAgent ? 'bg-primary' : isBot ? 'bg-muted text-muted-foreground' : 'bg-info'
        )}
      >
        {avatarLetter}
      </div>

      {/* Content */}
      <div className={cn('flex min-w-0 max-w-[70%] flex-col', isOwn ? 'items-end' : 'items-start')}>
        {senderLabel && (
          <div className={cn('mb-0.5 text-xs text-muted-foreground', isOwn && 'text-right')}>
            {senderLabel}
          </div>
        )}
        {message.content_type === 'image' || message.content_type === 'file' ? (
          <MessageAttachment
            conversationId={message.conversation_id}
            contentType={message.content_type}
            content={message.content}
          />
        ) : message.content_type === 'rich_text' ? (
          <RichTextMessageContent
            html={message.content}
            conversationId={message.conversation_id}
            className={cn(
              'max-w-full rounded-lg px-3 py-2 text-sm break-words break-all',
              isAgent ? 'bg-primary text-primary-foreground' : 'bg-secondary text-foreground',
            )}
          />
        ) : hasOpenAgentTrace ? (
          <div className="w-full min-w-0 space-y-2">
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
              'max-w-full rounded-lg px-3 py-2 text-sm break-words break-all whitespace-pre-wrap',
              isAgent ? 'bg-primary text-primary-foreground' : 'bg-secondary text-foreground',
              isBot && [markdownTextRootClass, richTextListStyleClass],
            )}
          >
            {isBot ? <MarkdownText>{stripOpenAgentThinkSections(message.content)}</MarkdownText> : message.content}
          </div>
        )}
        <div
          className={cn('mt-0.5 cursor-default text-[10px] text-muted-foreground', isOwn && 'text-right')}
          title={formatFullTime(message.created_at)}
        >
          {formatTime(message.created_at)}
        </div>
        {isBot && (
          <OpenAgentFeedbackStatus
            messageId={message.id}
            senderType={message.sender_type}
            metadata={message.metadata}
            locale={locale}
            align={isOwn ? 'end' : 'start'}
          />
        )}
      </div>
    </div>
  )
}
