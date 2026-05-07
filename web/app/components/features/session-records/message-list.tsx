'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { IconLoader2 } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useSessionRecordMessages } from '@/service/use-session-records'
import { MessageAttachment } from '@/app/components/features/chat/message-attachment'
import type { SessionRecordMessage } from '@/models/session-record'

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function formatFullTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleString('sv-SE').replace('T', ' ')
}

type Props = {
  recordId: number
}

export function MessageList({ recordId }: Props) {
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
            <MessageBubble key={msg.id} message={msg} />
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

function MessageBubble({ message }: { message: SessionRecordMessage }) {
  const [showFullTime, setShowFullTime] = useState(false)
  const isSystem = message.sender_type === 'system' || message.content_type === 'system'
  const isAgent = message.sender_type === 'agent'
  const isOwn = isAgent

  if (isSystem) {
    return (
      <div className="my-3 text-center">
        <span className="rounded-full bg-secondary px-3 py-1 text-xs text-muted-foreground">
          {message.content}
        </span>
      </div>
    )
  }

  const avatarLetter = (message.sender_name || (isAgent ? 'A' : 'V')).charAt(0).toUpperCase()

  return (
    <div className={cn('mb-3 flex gap-2', isOwn ? 'flex-row-reverse' : 'flex-row')}>
      {/* Avatar */}
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-medium text-white',
          isAgent ? 'bg-primary' : 'bg-info'
        )}
      >
        {avatarLetter}
      </div>

      {/* Content */}
      <div className={cn('max-w-[70%]', isOwn ? 'items-end' : 'items-start')}>
        <div className={cn('mb-0.5 text-xs text-muted-foreground', isOwn && 'text-right')}>
          {message.sender_name}
        </div>
        {message.content_type === 'image' || message.content_type === 'file' ? (
          <MessageAttachment
            conversationId={message.conversation_id}
            contentType={message.content_type}
            content={message.content}
          />
        ) : (
          <div
            className={cn(
              'whitespace-pre-wrap rounded-lg px-3 py-2 text-sm',
              isOwn ? 'bg-primary text-primary-foreground' : 'bg-secondary text-foreground'
            )}
          >
            {message.content}
          </div>
        )}
        <div
          className={cn('mt-0.5 cursor-default text-[10px] text-muted-foreground', isOwn && 'text-right')}
          title={formatFullTime(message.created_at)}
        >
          {formatTime(message.created_at)}
        </div>
      </div>
    </div>
  )
}
