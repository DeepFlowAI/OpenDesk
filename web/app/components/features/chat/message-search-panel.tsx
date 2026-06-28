'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { IconInfoCircle, IconLoader2, IconSearch, IconX } from '@tabler/icons-react'
import { useWorkspaceConversationHistory } from '@/service/use-conversations'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { cn } from '@/lib/utils'
import { isConversationHistoryContentMessage } from '@/lib/conversation-history-message'
import { richTextPreview } from '@/lib/rich-text-message'
import { isWelcomeLikeContentType } from '@/lib/welcome-message-content-type'
import { SessionDetailDrawer } from '@/app/components/features/session-records/session-detail-drawer'
import type { Conversation, Message, WorkspaceConversationHistoryItem } from '@/models/conversation'

type Props = {
  conversation: Conversation | null
  width: number
  onClose: () => void
}

const MAX_SEARCH_LENGTH = 100

function useDebouncedValue(value: string): string {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), 300)
    return () => window.clearTimeout(timer)
  }, [value])

  return debounced
}

function formatPanelTime(dateStr: string | null | undefined, locale: 'zh' | 'en'): string {
  if (!dateStr) return locale === 'zh' ? '未知时间' : 'Unknown time'
  const date = new Date(dateStr)
  return date.toLocaleString(locale === 'zh' ? 'zh-CN' : 'en-US', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}

function highlightText(text: string, keyword: string) {
  const query = keyword.trim()
  if (!query) return text
  const lower = text.toLowerCase()
  const lowerQuery = query.toLowerCase()
  const parts: Array<{ text: string; hit: boolean }> = []
  let cursor = 0

  while (cursor < text.length) {
    const index = lower.indexOf(lowerQuery, cursor)
    if (index < 0) {
      parts.push({ text: text.slice(cursor), hit: false })
      break
    }
    if (index > cursor) {
      parts.push({ text: text.slice(cursor, index), hit: false })
    }
    parts.push({ text: text.slice(index, index + query.length), hit: true })
    cursor = index + query.length
  }

  return parts.map((part, index) => (
    part.hit ? (
      <mark key={index} className="rounded-sm bg-warning/20 px-0.5 text-foreground">
        {part.text}
      </mark>
    ) : (
      <span key={index}>{part.text}</span>
    )
  ))
}

function senderLabel(message: Message, locale: 'zh' | 'en'): string {
  if (isWelcomeLikeContentType(message.content_type)) return locale === 'zh' ? '欢迎语' : 'Welcome'
  if (message.sender_name) return message.sender_name
  if (message.sender_type === 'visitor') return locale === 'zh' ? '访客' : 'Visitor'
  if (message.sender_type === 'agent') return locale === 'zh' ? '客服' : 'Agent'
  if (message.sender_type === 'bot') return locale === 'zh' ? '机器人' : 'Bot'
  return locale === 'zh' ? '系统' : 'System'
}

function renderMessageContent(message: Message, keyword: string, locale: 'zh' | 'en') {
  if (message.content_type === 'image') return t('ws.chat.image', locale)
  if (message.content_type === 'file') return locale === 'zh' ? '[文件]' : '[File]'
  if (message.content_type === 'rich_text' || isWelcomeLikeContentType(message.content_type)) {
    return highlightText(richTextPreview(message.content, locale), keyword)
  }
  if (message.content_type === 'satisfaction_event') return message.content
  return highlightText(message.content, keyword)
}

function conversationTitle(conversation: WorkspaceConversationHistoryItem, locale: 'zh' | 'en'): string {
  const startedAt = formatPanelTime(
    conversation.started_at || conversation.created_at || conversation.last_message_at,
    locale,
  )
  const channel = conversation.channel?.name || conversation.channel?.channel_type || '-'
  const status = t(`ws.chat.status.${conversation.status}`, locale)
  return `${startedAt} · ${channel} · ${status}`
}

function ConversationBlock({
  conversation,
  keyword,
  locale,
  onOpenDetail,
}: {
  conversation: WorkspaceConversationHistoryItem
  keyword: string
  locale: 'zh' | 'en'
  onOpenDetail: (recordId: number) => void
}) {
  const visibleMessages = useMemo(
    () => conversation.messages.filter(isConversationHistoryContentMessage),
    [conversation.messages],
  )
  const detailLabel = locale === 'zh' ? '查看会话详情' : 'View conversation details'

  return (
    <section className="border-b border-border/70 px-4 py-3">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="min-w-0 truncate text-[11px] font-medium text-muted-foreground">
          {conversationTitle(conversation, locale)}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {conversation.messages_truncated && (
            <span className="text-[11px] text-muted-foreground">
              {locale === 'zh' ? '仅显示最近 200 条' : 'Latest 200 only'}
            </span>
          )}
          <button
            type="button"
            onClick={() => onOpenDetail(conversation.id)}
            className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label={detailLabel}
            title={detailLabel}
          >
            <IconInfoCircle size={16} stroke={1.7} />
          </button>
        </div>
      </div>
      <div className="space-y-1.5">
        {visibleMessages.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            {locale === 'zh' ? '该会话暂无消息' : 'No messages in this conversation'}
          </p>
        ) : (
          visibleMessages.map((message) => {
            const internal = message.content_type === 'internal_note'
            return (
              <div key={message.id} className="flex gap-2 text-[12px] leading-5">
                <span className="w-11 shrink-0 text-right text-muted-foreground">
                  {formatPanelTime(message.created_at, locale).slice(-5)}
                </span>
                <div className="min-w-0 flex-1">
                  <span className="font-medium text-muted-foreground">
                    {senderLabel(message, locale)}
                  </span>
                  <span className="mx-1 text-muted-foreground">:</span>
                  {internal && (
                    <span className="mr-1 rounded-sm bg-warning/15 px-1 text-[11px] text-foreground">
                      {t('ws.chat.messageSearch.internal', locale)}
                    </span>
                  )}
                  <span
                    className={cn(
                      'break-words text-foreground',
                      message.sender_type === 'system' && 'text-muted-foreground',
                    )}
                  >
                    {renderMessageContent(message, keyword, locale)}
                  </span>
                </div>
              </div>
            )
          })
        )}
      </div>
    </section>
  )
}

export function MessageSearchPanel({
  conversation,
  width,
  onClose,
}: Props) {
  const { locale } = useLocaleStore()
  const inputRef = useRef<HTMLInputElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const autoScrolledKeyRef = useRef<string | null>(null)
  const [query, setQuery] = useState('')
  const [lengthError, setLengthError] = useState(false)
  const [selectedRecordId, setSelectedRecordId] = useState<number | null>(null)
  const debouncedQuery = useDebouncedValue(query)
  const historyQuery = useWorkspaceConversationHistory(conversation?.id ?? 0, debouncedQuery, {
    enabled: Boolean(conversation?.id),
  })
  const conversations = useMemo(
    () => [...(historyQuery.data?.pages.flatMap((page) => page.items) ?? [])].reverse(),
    [historyQuery.data?.pages],
  )
  const visibleConversations = useMemo(
    () => conversations.filter((item) => item.messages.some(isConversationHistoryContentMessage)),
    [conversations],
  )
  const visitorName = conversation?.visitor?.name || conversation?.visitor?.external_id || conversation?.share_code || '-'
  const hasKeyword = debouncedQuery.trim().length > 0
  const loadedCount = visibleConversations.length

  useEffect(() => {
    inputRef.current?.focus()
  }, [conversation?.id])

  useEffect(() => {
    setQuery('')
    setLengthError(false)
    setSelectedRecordId(null)
    autoScrolledKeyRef.current = null
  }, [conversation?.id])

  useEffect(() => {
    autoScrolledKeyRef.current = null
  }, [debouncedQuery])

  useEffect(() => {
    const key = `${conversation?.id ?? 0}:${debouncedQuery.trim()}`
    const viewport = scrollRef.current
    if (!viewport || historyQuery.isLoading || autoScrolledKeyRef.current === key) return
    viewport.scrollTop = viewport.scrollHeight
    autoScrolledKeyRef.current = key
  }, [conversation?.id, visibleConversations.length, debouncedQuery, historyQuery.isLoading])

  const handleChange = (value: string) => {
    if (value.length > MAX_SEARCH_LENGTH) {
      setLengthError(true)
      setQuery(value.slice(0, MAX_SEARCH_LENGTH))
      return
    }
    setLengthError(false)
    setQuery(value)
  }

  return (
    <div className="flex shrink-0 flex-col border-l border-border bg-background" style={{ width }}>
      <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border px-4">
        <div className="min-w-0">
          <h2 className="truncate text-sm font-semibold text-foreground">
            {t('ws.chat.messageSearch.title', locale)}
          </h2>
          <p className="truncate text-xs text-muted-foreground" title={visitorName}>
            {visitorName}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label={t('ws.chat.messageSearch.close', locale)}
          title={t('ws.chat.messageSearch.close', locale)}
        >
          <IconX size={18} stroke={1.6} />
        </button>
      </div>

      <div className="shrink-0 border-b border-border px-4 py-3">
        <div className="flex h-9 items-center gap-2 rounded-md border border-input bg-background px-2.5">
          <IconSearch size={16} stroke={1.6} className="shrink-0 text-muted-foreground" />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(event) => handleChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                setQuery((current) => current.trim())
              }
            }}
            placeholder={t('ws.chat.messageSearch.placeholder', locale)}
            className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
          {query && (
            <button
              type="button"
              onClick={() => {
                setQuery('')
                setLengthError(false)
                inputRef.current?.focus()
              }}
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground"
              aria-label={t('ws.chat.messageSearch.clear', locale)}
              title={t('ws.chat.messageSearch.clear', locale)}
            >
              <IconX size={14} stroke={1.6} />
            </button>
          )}
          {historyQuery.isFetching && (
            <IconLoader2 size={15} stroke={1.6} className="shrink-0 animate-spin text-muted-foreground" />
          )}
        </div>
        {lengthError && (
          <p className="mt-2 text-xs text-destructive">
            {t('ws.chat.messageSearch.tooLong', locale)}
          </p>
        )}
        <div className="mt-3 flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <span>
            {hasKeyword
              ? t('ws.chat.messageSearch.resultsCount', locale, { count: loadedCount })
              : t('ws.chat.messageSearch.recent', locale)}
          </span>
          <span>{t('ws.chat.messageSearch.scopeHint', locale)}</span>
        </div>
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {historyQuery.isLoading ? (
          <div className="flex flex-col gap-3 px-4 py-3">
            {Array.from({ length: 5 }).map((_, index) => (
              <div key={index} className="space-y-2 border-b border-border/70 pb-3">
                <div className="h-3 w-3/4 animate-pulse rounded bg-muted" />
                <div className="h-3 w-full animate-pulse rounded bg-muted" />
                <div className="h-3 w-5/6 animate-pulse rounded bg-muted" />
              </div>
            ))}
          </div>
        ) : historyQuery.isError ? (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-muted-foreground">
              {t('ws.chat.messageSearch.loadFailed', locale)}
            </p>
            <button
              type="button"
              onClick={() => void historyQuery.refetch()}
              className="mt-2 text-xs font-medium text-primary hover:underline"
            >
              {t('ws.chat.retry', locale)}
            </button>
          </div>
        ) : visibleConversations.length === 0 && !historyQuery.hasNextPage ? (
          <div className="px-4 py-8 text-center">
            <p className="text-sm text-muted-foreground">
              {hasKeyword
                ? t('ws.chat.messageSearch.noMatches', locale)
                : t('ws.chat.messageSearch.empty', locale)}
            </p>
          </div>
        ) : (
          <div>
            {historyQuery.hasNextPage && (
              <div className="border-b border-border/70 px-4 py-3">
                <button
                  type="button"
                  onClick={() => void historyQuery.fetchNextPage()}
                  disabled={historyQuery.isFetchingNextPage}
                  className="flex h-8 w-full items-center justify-center gap-1.5 rounded-md border border-border text-xs font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:text-muted-foreground"
                >
                  {historyQuery.isFetchingNextPage && <IconLoader2 size={14} className="animate-spin" />}
                  {t('ws.chat.messageSearch.loadMore', locale)}
                </button>
              </div>
            )}
            {visibleConversations.map((item) => (
              <ConversationBlock
                key={item.id}
                conversation={item}
                keyword={debouncedQuery}
                locale={locale}
                onOpenDetail={setSelectedRecordId}
              />
            ))}
          </div>
        )}
      </div>

      {selectedRecordId != null && (
        <SessionDetailDrawer
          recordId={selectedRecordId}
          onClose={() => setSelectedRecordId(null)}
        />
      )}
    </div>
  )
}
