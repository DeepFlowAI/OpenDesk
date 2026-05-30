'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { IconChevronRight, IconLoader2, IconTool } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { useLocaleStore } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import { useSessionRecordMessages } from '@/service/use-session-records'
import { MessageAttachment } from '@/app/components/features/chat/message-attachment'
import { WelcomeMessage } from '@/app/components/features/visitor-chat/welcome-message'
import { MarkdownText, markdownTextRootClass } from '@/components/assistant-ui/markdown-text'
import type { OpenAgentTextBlock, OpenAgentThinkingBlock as OpenAgentThinkingBlockType, OpenAgentToolBlock } from '@/models/conversation'
import type { SessionRecordMessage } from '@/models/session-record'
import { resolveOpenAgentHandoffEventLabel } from '@/lib/open-agent-handoff-event'

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
}

function formatFullTime(dateStr: string): string {
  const d = new Date(dateStr)
  return d.toLocaleString('sv-SE').replace('T', ' ')
}

const BOT_BUBBLE_CLASS = 'rounded-lg bg-secondary px-3 py-2 text-sm text-foreground break-words'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function getStringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function getNumberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function stripOpenAgentThinkSections(content: string): string {
  return content
    .replace(/<think>[\s\S]*?<\/think>/gi, '')
    .replace(/<think>[\s\S]*$/gi, '')
    .replace(/<\/think>/gi, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function isHumanHandoffToolBlock(block: OpenAgentToolBlock): boolean {
  return block.toolName.trim().toLowerCase() === 'human_handoff'
}

function getOpenAgentThinkingBlocks(metadata?: Record<string, unknown>): OpenAgentThinkingBlockType[] {
  const value = metadata?.open_agent_thinking_blocks
  if (!Array.isArray(value)) return []

  return value.flatMap((item): OpenAgentThinkingBlockType[] => {
    if (!isRecord(item)) return []
    const id = getStringValue(item.id)
    if (!id) return []
    return [{
      id,
      content: getStringValue(item.content),
      llmStepId: getNumberValue(item.llmStepId) ?? getNumberValue(item.llm_step_id),
      isStreaming: item.isStreaming === true || item.is_streaming === true,
      timelineIndex: getNumberValue(item.timelineIndex) ?? getNumberValue(item.timeline_index) ?? 0,
    }]
  })
}

function getOpenAgentToolBlocks(metadata?: Record<string, unknown>): OpenAgentToolBlock[] {
  const value = metadata?.open_agent_tool_blocks
  if (!Array.isArray(value)) return []

  return value.flatMap((item): OpenAgentToolBlock[] => {
    if (!isRecord(item)) return []
    const toolCallId = getStringValue(item.toolCallId) || getStringValue(item.tool_call_id)
    const toolName = getStringValue(item.toolName) || getStringValue(item.tool_name)
    const id = getStringValue(item.id) || (toolCallId ? `tool_${toolCallId}` : '')
    if (!id || !toolCallId) return []
    return [{
      id,
      toolName,
      brief: getStringValue(item.brief) || toolName || '工具调用',
      toolCallId,
      stepId: getNumberValue(item.stepId) ?? getNumberValue(item.step_id),
      isExecuting: item.isExecuting === true || item.is_executing === true,
      timelineIndex: getNumberValue(item.timelineIndex) ?? getNumberValue(item.timeline_index) ?? 0,
      arguments: item.arguments ?? item.args,
      result: item.result,
    }]
  })
}

function getOpenAgentTextBlocks(metadata?: Record<string, unknown>): OpenAgentTextBlock[] {
  const value = metadata?.open_agent_text_blocks
  if (!Array.isArray(value)) return []

  return value.flatMap((item): OpenAgentTextBlock[] => {
    if (!isRecord(item)) return []
    const id = getStringValue(item.id)
    const content = getStringValue(item.content)
    if (!id || content.length === 0) return []
    return [{
      id,
      content,
      isStreaming: item.isStreaming === true || item.is_streaming === true,
      timelineIndex: getNumberValue(item.timelineIndex) ?? getNumberValue(item.timeline_index) ?? 0,
    }]
  })
}

function OpenAgentThinkingBlock({
  locale,
  active = false,
  content = '',
}: {
  locale: string
  active?: boolean
  content?: string
}) {
  const [expanded, setExpanded] = useState(true)
  const hasContent = content.trim().length > 0

  return (
    <div className="w-full rounded-lg bg-[#F6F6F6] text-sm text-[#71717A]" data-open-agent-thinking>
      <button
        type="button"
        className="flex min-h-9 w-full items-center justify-between gap-2 px-3 py-2 text-left"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <span className="flex min-w-0 items-center gap-2 font-medium">
          <IconChevronRight
            size={16}
            className={cn('shrink-0 transition-transform', expanded && 'rotate-90')}
            aria-hidden
          />
          <span>{locale === 'zh' ? '思考' : 'Thinking'}</span>
          {active && (
            <span className="inline-flex h-4 items-center gap-1" aria-hidden="true">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-current opacity-70 motion-safe:animate-bounce [animation-delay:0ms] [animation-duration:900ms]" />
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-current opacity-70 motion-safe:animate-bounce [animation-delay:150ms] [animation-duration:900ms]" />
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-current opacity-70 motion-safe:animate-bounce [animation-delay:300ms] [animation-duration:900ms]" />
            </span>
          )}
        </span>
      </button>
      {expanded && hasContent && (
        <div className="whitespace-pre-wrap break-words px-3 pb-3 pl-9 text-xs leading-5 text-[#52525B]">
          {content}
        </div>
      )}
    </div>
  )
}

function OpenAgentToolBlockView({ block, locale }: { block: OpenAgentToolBlock; locale: string }) {
  return (
    <div
      className="flex min-h-10 w-full items-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#27272A] shadow-sm"
      data-open-agent-tool-call
    >
      <IconTool size={16} className="shrink-0 text-[#71717A]" aria-hidden />
      <span className="min-w-0 flex-1 truncate">
        {block.brief || block.toolName || (locale === 'zh' ? '工具调用' : 'Tool call')}
      </span>
      {block.isExecuting && (
        <IconLoader2 size={16} className="shrink-0 animate-spin text-[#A1A1AA]" aria-hidden />
      )}
    </div>
  )
}

function OpenAgentTextBlockView({
  content,
}: {
  content: string
}) {
  const displayContent = stripOpenAgentThinkSections(content)
  if (!displayContent) return null

  return (
    <div
      className={cn(BOT_BUBBLE_CLASS, markdownTextRootClass, richTextListStyleClass)}
      data-open-agent-final
    >
      <MarkdownText>{displayContent}</MarkdownText>
    </div>
  )
}

function OpenAgentTraceBlocks({
  textBlocks,
  thinkingBlocks,
  toolBlocks,
  locale,
}: {
  textBlocks: OpenAgentTextBlock[]
  thinkingBlocks: OpenAgentThinkingBlockType[]
  toolBlocks: OpenAgentToolBlock[]
  locale: string
}) {
  const traceBlocks = [
    ...textBlocks.map((block) => ({ type: 'text' as const, block, timelineIndex: block.timelineIndex })),
    ...thinkingBlocks.map((block) => ({ type: 'thinking' as const, block, timelineIndex: block.timelineIndex })),
    ...toolBlocks.map((block) => ({ type: 'tool' as const, block, timelineIndex: block.timelineIndex })),
  ].sort((a, b) => a.timelineIndex - b.timelineIndex)

  if (traceBlocks.length === 0) return null

  return (
    <div className="space-y-2">
      {textBlocks.length === 0 && thinkingBlocks.length === 0 && toolBlocks.length > 0 && (
        <OpenAgentThinkingBlock locale={locale} />
      )}
      {traceBlocks.map((item) => (
        item.type === 'text' ? (
          <OpenAgentTextBlockView key={item.block.id} content={item.block.content} />
        ) : item.type === 'thinking' ? (
          <OpenAgentThinkingBlock
            key={item.block.id}
            locale={locale}
            active={item.block.isStreaming}
            content={item.block.content}
          />
        ) : (
          <OpenAgentToolBlockView key={item.block.id} block={item.block} locale={locale} />
        )
      ))}
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
  const toolBlocks = isBot ? getOpenAgentToolBlocks(message.metadata) : []
  const visibleToolBlocks = toolBlocks.filter((block) => !isHumanHandoffToolBlock(block))
  const hasOpenAgentTrace =
    isBot && (textBlocks.length > 0 || thinkingBlocks.length > 0 || visibleToolBlocks.length > 0)

  if (message.content_type === 'welcome') {
    return (
      <div className="my-3">
        <WelcomeMessage content={message.content} />
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
          {message.content}
        </button>
      </div>
    )
  }

  if (isSystem) {
    const handoffEventLabel = resolveOpenAgentHandoffEventLabel(message.metadata, locale)
    return (
      <div className="my-3 text-center">
        <span className="rounded-full bg-secondary px-3 py-1 text-xs text-muted-foreground">
          {handoffEventLabel || message.content}
        </span>
      </div>
    )
  }

  const senderName = message.sender_name || (isBot ? '智能助手' : isAgent ? 'A' : 'V')
  const avatarLetter = senderName.charAt(0).toUpperCase()

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
      <div className={cn('flex max-w-[70%] flex-col', isOwn ? 'items-end' : 'items-start')}>
        <div className={cn('mb-0.5 text-xs text-muted-foreground', isOwn && 'text-right')}>
          {senderName}
        </div>
        {message.content_type === 'image' || message.content_type === 'file' ? (
          <MessageAttachment
            conversationId={message.conversation_id}
            contentType={message.content_type}
            content={message.content}
          />
        ) : hasOpenAgentTrace ? (
          <div className="w-full space-y-2">
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
              'rounded-lg px-3 py-2 text-sm break-words',
              isAgent ? 'bg-primary text-primary-foreground' : 'bg-secondary text-foreground',
              isBot ? [markdownTextRootClass, richTextListStyleClass] : 'whitespace-pre-wrap'
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
      </div>
    </div>
  )
}
