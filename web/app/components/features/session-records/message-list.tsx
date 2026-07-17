'use client'

import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { IconLoader2 } from '@tabler/icons-react'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useSessionRecordMessages } from '@/service/use-session-records'
import {
  WorkspaceMessageBubble,
  sessionRecordMessageToMessage,
} from '@/app/components/features/chat/workspace-message-bubble'
import type { SessionRecordMessage } from '@/models/session-record'

type Props = {
  recordId: number
  onSatisfactionEventClick?: () => void
}

export function MessageList({ recordId, onSatisfactionEventClick }: Props) {
  const { locale } = useLocaleStore()
  const [allMessages, setAllMessages] = useState<SessionRecordMessage[]>([])
  const [afterId, setAfterId] = useState<number | undefined>(undefined)
  const [hasMore, setHasMore] = useState(true)
  const [, setLoadCount] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)

  const { data, isLoading, isError } = useSessionRecordMessages(recordId, afterId)

  const mappedMessages = useMemo(
    () => allMessages.map(sessionRecordMessageToMessage),
    [allMessages],
  )

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
          {mappedMessages.map((msg) => (
            <WorkspaceMessageBubble
              key={msg.id}
              message={msg}
              locale={locale}
              mode="record"
              attachmentContext={{ kind: 'conversation', conversationId: msg.conversation_id }}
              allMessages={mappedMessages}
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
