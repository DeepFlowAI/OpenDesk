'use client'

import type { Message, OpenAgentTextBlock, OpenAgentToolBlock } from '@/models/conversation'
import type { ChannelConfig } from '@/models/channel'
import { useMemo, useState, type CSSProperties, type PropsWithChildren } from 'react'
import {
  MessagePrimitive,
  type EmptyMessagePartProps,
  type ReasoningMessagePartProps,
  type TextMessagePartProps,
  type ToolCallMessagePartProps,
} from '@assistant-ui/react'
import { MessageAttachment } from '@/app/components/features/chat/message-attachment'
import {
  getOpenAgentThinkingBlocks,
  getOpenAgentTextBlocks,
  getOpenAgentToolBlocks,
  useVisitorChatConfig,
} from '@/components/assistant-ui/visitor-chat-runtime'
import { AssistantMarkdownText, MarkdownText, markdownTextRootClass } from '@/components/assistant-ui/markdown-text'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { cn } from '@/lib/utils'
import { IconChevronRight, IconLoader2, IconTool } from '@tabler/icons-react'

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
  renderAssistantParts?: boolean
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

type OpenAgentToolArtifact = {
  brief?: unknown
  isExecuting?: unknown
  timelineIndex?: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function getToolArtifact(value: unknown): OpenAgentToolArtifact {
  return isRecord(value) ? value : {}
}

function getToolBriefFromArgs(args: unknown): string {
  if (!isRecord(args)) return ''
  const query = args.query
  if (typeof query === 'string' && query.trim()) return query.trim()
  const input = args.input
  if (typeof input === 'string' && input.trim()) return input.trim()
  const q = args.q
  if (typeof q === 'string' && q.trim()) return q.trim()
  return ''
}

function getToolDisplayName(toolName: string, locale: string): string {
  if (!toolName || toolName === 'open_agent_tool') {
    return locale === 'zh' ? '工具调用' : 'Tool call'
  }
  return toolName
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
  const label = locale === 'zh' ? '思考' : 'Thinking'
  const hasContent = content.trim().length > 0

  return (
    <div
      className="w-full rounded-lg bg-[#F6F6F6] text-sm text-[#71717A]"
      data-open-agent-thinking
    >
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
          <span>{label}</span>
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

function OpenAgentToolSurface({
  label,
  executing,
  locale,
}: {
  label: string
  executing?: boolean
  locale: string
}) {
  return (
    <div
      className="flex min-h-10 w-full items-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#27272A] shadow-sm"
      data-open-agent-tool-call
    >
      <IconTool size={16} className="shrink-0 text-[#71717A]" aria-hidden />
      <span className="min-w-0 flex-1 truncate">
        {label || (locale === 'zh' ? '工具调用' : 'Tool call')}
      </span>
      {executing && (
        <IconLoader2 size={16} className="shrink-0 animate-spin text-[#A1A1AA]" aria-hidden />
      )}
    </div>
  )
}

function OpenAgentToolPart({
  toolName,
  args,
  artifact,
  status,
  locale,
}: ToolCallMessagePartProps & { locale: string }) {
  const toolArtifact = getToolArtifact(artifact)
  const brief = typeof toolArtifact.brief === 'string' && toolArtifact.brief.trim()
    ? toolArtifact.brief.trim()
    : getToolBriefFromArgs(args)
  const label = brief || getToolDisplayName(toolName, locale)
  const executing = toolArtifact.isExecuting === true || status?.type === 'running'

  return <OpenAgentToolSurface label={label} executing={executing} locale={locale} />
}

function StaticToolCallBlock({
  block,
  locale,
}: {
  block: OpenAgentToolBlock
  locale: string
}) {
  return (
    <OpenAgentToolSurface
      label={block.brief || block.toolName || (locale === 'zh' ? '工具调用' : 'Tool call')}
      executing={block.isExecuting}
      locale={locale}
    />
  )
}

function StaticOpenAgentTraceBlocks({
  textBlocks,
  thinkingBlocks,
  toolBlocks,
  locale,
  bubbleStyle,
}: {
  textBlocks: OpenAgentTextBlock[]
  thinkingBlocks: ReturnType<typeof getOpenAgentThinkingBlocks>
  toolBlocks: OpenAgentToolBlock[]
  locale: string
  bubbleStyle: CSSProperties
}) {
  const traceBlocks = [
    ...textBlocks.map((block) => ({ type: 'text' as const, block, timelineIndex: block.timelineIndex })),
    ...thinkingBlocks.map((block) => ({ type: 'thinking' as const, block, timelineIndex: block.timelineIndex })),
    ...toolBlocks.map((block) => ({ type: 'tool' as const, block, timelineIndex: block.timelineIndex })),
  ].sort((a, b) => a.timelineIndex - b.timelineIndex)

  if (traceBlocks.length === 0 && toolBlocks.length === 0) return null

  return (
    <div className="space-y-2">
      {textBlocks.length === 0 && thinkingBlocks.length === 0 && toolBlocks.length > 0 && (
        <OpenAgentThinkingBlock locale={locale} />
      )}
      {traceBlocks.map((item) => (
        item.type === 'text' ? (
          <StaticOpenAgentTextBlock
            key={item.block.id}
            content={item.block.content}
            bubbleStyle={bubbleStyle}
          />
        ) : item.type === 'thinking' ? (
          <OpenAgentThinkingBlock
            key={item.block.id}
            locale={locale}
            active={item.block.isStreaming}
            content={item.block.content}
          />
        ) : (
          <StaticToolCallBlock key={item.block.id} block={item.block} locale={locale} />
        )
      ))}
    </div>
  )
}

function OpenAgentTextPart({
  bubbleStyle,
}: TextMessagePartProps & { bubbleStyle: CSSProperties }) {
  return (
    <div
      className={cn(
        'min-h-[42px] w-full min-w-0 break-words break-all px-3 py-2 text-sm leading-6 whitespace-pre-wrap',
        markdownTextRootClass,
        richTextListStyleClass,
      )}
      style={bubbleStyle}
      data-open-agent-final
    >
      <AssistantMarkdownText />
    </div>
  )
}

function StaticOpenAgentTextBlock({
  content,
  bubbleStyle,
}: {
  content: string
  bubbleStyle: CSSProperties
}) {
  if (content.trim().length === 0) return null

  return (
    <div
      className={cn(
        'min-h-[42px] w-full min-w-0 break-words break-all px-3 py-2 text-sm leading-6 whitespace-pre-wrap',
        markdownTextRootClass,
        richTextListStyleClass,
      )}
      style={bubbleStyle}
      data-open-agent-final
    >
      <MarkdownText>{content}</MarkdownText>
    </div>
  )
}

function PartsGroup({ children }: PropsWithChildren) {
  return <div className="space-y-2">{children}</div>
}

function isHumanHandoffToolBlock(block: OpenAgentToolBlock): boolean {
  return block.toolName.trim().toLowerCase() === 'human_handoff' || block.usedForHandoff === true
}

export function MessageBubble({
  message,
  config,
  showAvatar,
  showName,
  locale,
  messageStatus,
  showTime = true,
  renderAssistantParts = false,
}: MessageBubbleProps) {
  const isUser = message.sender_type === 'visitor'
  const isAssistant = message.sender_type === 'agent' || message.sender_type === 'bot'
  const isBot = message.sender_type === 'bot'
  const visitorChat = useVisitorChatConfig()
  const statusText = isUser ? statusLabel(messageStatus || message.status, locale) : null
  const textBlocks = isBot ? getOpenAgentTextBlocks(message.metadata) : []
  const thinkingBlocks = isBot ? getOpenAgentThinkingBlocks(message.metadata) : []
  const toolBlocks = isBot ? getOpenAgentToolBlocks(message.metadata) : []
  const visibleToolBlocks = toolBlocks.filter((block) => !isHumanHandoffToolBlock(block))
  const hasMessageText = message.content.trim().length > 0
  const hasVisibleOpenAgentBlocks =
    textBlocks.length > 0 || thinkingBlocks.length > 0 || visibleToolBlocks.length > 0
  const isThinking =
    isBot
    && message.metadata?.streaming === true
    && !renderAssistantParts
    && !hasMessageText
    && visibleToolBlocks.length === 0

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

  const assistantPartsComponents = useMemo(
    () => ({
      Text: (props: TextMessagePartProps) => (
        <OpenAgentTextPart {...props} bubbleStyle={bubbleStyle} />
      ),
      Reasoning: (props: ReasoningMessagePartProps) => (
        <OpenAgentThinkingBlock
          locale={locale}
          active={props.status?.type === 'running'}
          content={props.text === 'thinking' ? '' : props.text}
        />
      ),
      Empty: ({ status }: EmptyMessagePartProps) => (
        status.type === 'running'
          ? <OpenAgentThinkingBlock locale={locale} active />
          : null
      ),
      ToolGroup: PartsGroup,
      ReasoningGroup: PartsGroup,
      tools: {
        Fallback: (props: ToolCallMessagePartProps) => {
          if (props.toolName?.trim().toLowerCase() === 'human_handoff') return null
          return <OpenAgentToolPart {...props} locale={locale} />
        },
      },
    }),
    [bubbleStyle, locale],
  )

  const attachmentContentType =
    message.content_type === 'image' ? 'image' : message.content_type === 'file' ? 'file' : null
  const isEmptyBotBubble =
    isBot
    && !attachmentContentType
    && !isThinking
    && !hasVisibleOpenAgentBlocks
    && !hasMessageText
  const isEmptyAssistantBubble =
    isAssistant
    && !isBot
    && !attachmentContentType
    && !hasMessageText

  if (isEmptyBotBubble || isEmptyAssistantBubble) return null

  if (isBot && !attachmentContentType && renderAssistantParts) {
    return (
      <div className="flex flex-row items-start gap-2 px-5">
        {showAvatar && (
          <img
            src={message.sender_avatar || DEFAULT_AGENT_AVATAR_SRC}
            alt={message.sender_name || ''}
            className="h-9 w-9 shrink-0 rounded-full object-cover"
          />
        )}

        <div className="flex w-full min-w-0 max-w-[75%] flex-col items-start">
          {showName && message.sender_name && (
            <span className="mb-1 text-xs font-medium text-muted-foreground">
              {message.sender_name}
            </span>
          )}

          <div className="w-full min-w-0 space-y-2">
            <MessagePrimitive.Parts components={assistantPartsComponents} />
          </div>

          {showTime && (
            <div className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
              <span>{formatTime(message.created_at, locale)}</span>
            </div>
          )}
        </div>
      </div>
    )
  }

  if (
    isBot
    && !attachmentContentType
    && (isThinking || textBlocks.length > 0 || thinkingBlocks.length > 0 || visibleToolBlocks.length > 0)
  ) {
    return (
      <div className="flex flex-row items-start gap-2 px-5">
        {showAvatar && (
          <img
            src={message.sender_avatar || DEFAULT_AGENT_AVATAR_SRC}
            alt={message.sender_name || ''}
            className="h-9 w-9 shrink-0 rounded-full object-cover"
          />
        )}

        <div className="flex w-full min-w-0 max-w-[75%] flex-col items-start">
          {showName && message.sender_name && (
            <span className="mb-1 text-xs font-medium text-muted-foreground">
              {message.sender_name}
            </span>
          )}

          <div className="w-full min-w-0 space-y-2">
            {isThinking && thinkingBlocks.length === 0 && visibleToolBlocks.length === 0 && (
              <OpenAgentThinkingBlock locale={locale} active={isThinking} />
            )}
            <StaticOpenAgentTraceBlocks
              textBlocks={textBlocks}
              thinkingBlocks={thinkingBlocks}
              toolBlocks={visibleToolBlocks}
              locale={locale}
              bubbleStyle={bubbleStyle}
            />
            {textBlocks.length === 0 && (
              <StaticOpenAgentTextBlock content={message.content} bubbleStyle={bubbleStyle} />
            )}
          </div>

          {showTime && (
            <div className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
              <span>{formatTime(message.created_at, locale)}</span>
            </div>
          )}
        </div>
      </div>
    )
  }

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
      <div className={`flex min-w-0 max-w-[75%] flex-col ${isUser ? 'items-end' : 'items-start'}`}>
        {showName && isAssistant && message.sender_name && (
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
          <div
            className={cn(
              'min-h-[42px] max-w-full break-words break-all px-3 py-2 text-sm whitespace-pre-wrap',
              isBot && [markdownTextRootClass, richTextListStyleClass],
            )}
            style={bubbleStyle}
          >
            {isBot ? <MarkdownText>{message.content}</MarkdownText> : message.content}
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
