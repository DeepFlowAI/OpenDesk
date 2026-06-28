'use client'

import type { Message, OpenAgentTextBlock, OpenAgentToolBlock } from '@/models/conversation'
import type { ChannelConfig } from '@/models/channel'
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
  type MouseEvent as ReactMouseEvent,
  type PropsWithChildren,
  type TouchEvent as ReactTouchEvent,
} from 'react'
import {
  MessagePrimitive,
  type EmptyMessagePartProps,
  type ReasoningMessagePartProps,
  type TextMessagePartProps,
  type ToolCallMessagePartProps,
} from '@assistant-ui/react'
import { MessageAttachment } from '@/app/components/features/chat/message-attachment'
import { MessageQuoteBlock } from '@/app/components/features/chat/message-quote'
import { OpenAgentFeedback } from '@/app/components/features/chat/open-agent-feedback'
import { RichTextMessageContent } from '@/app/components/features/chat/rich-text-message-content'
import {
  getOpenAgentThinkingBlocks,
  getOpenAgentTextBlocks,
  getOpenAgentToolBlocks,
  useVisitorChatConfig,
} from '@/components/assistant-ui/visitor-chat-runtime'
import { AssistantMarkdownText, MarkdownText, markdownTextRootClass } from '@/components/assistant-ui/markdown-text'
import type { Locale } from '@/context/locale-store'
import {
  canQuoteMessage,
  messageQuoteFromMetadata,
} from '@/lib/message-quote'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { cn } from '@/lib/utils'
import { t } from '@/utils/i18n'
import { IconChevronRight, IconInfoCircle, IconLoader2, IconTool } from '@tabler/icons-react'
import { getAssistantAvatarSrc } from './avatar'

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
  allMessages?: Message[]
  onEditRecalledMessage?: (request: { text: string; contentType?: 'text' | 'rich_text'; quotedMessage?: Message | null }) => void
}

const MESSAGE_RECALL_WINDOW_MS = 2 * 60 * 1000

function isRecallableContentType(contentType: string): boolean {
  return contentType === 'text' || contentType === 'rich_text' || contentType === 'image' || contentType === 'file'
}

function isWithinRecallWindow(createdAt: string): boolean {
  const timestamp = Date.parse(createdAt)
  return !Number.isNaN(timestamp) && Date.now() - timestamp <= MESSAGE_RECALL_WINDOW_MS
}

function scrollToVisitorMessage(messageId: number, locale: string) {
  if (typeof document === 'undefined') return
  const node = document.querySelector<HTMLElement>(`[data-visitor-message-id="${messageId}"]`)
  if (!node) {
    window.alert(t('ws.chat.quote.locateFailed', locale as Locale))
    return
  }
  node.scrollIntoView({ block: 'center', behavior: 'smooth' })
  node.classList.add('bg-warning/15')
  window.setTimeout(() => {
    node.classList.remove('bg-warning/15')
  }, 1800)
}

export function shouldShowVisitorRecalledNotice(
  message: Pick<Message, 'is_recalled' | 'sender_type'>,
): boolean {
  return Boolean(message.is_recalled && message.sender_type === 'visitor')
}

function recallText(message: Message, locale: string): string {
  if (message.sender_type === 'visitor') {
    return locale === 'zh' ? '你撤回了一条消息' : 'You recalled a message'
  }
  if (message.sender_name) {
    return locale === 'zh'
      ? `${message.sender_name} 撤回了一条消息`
      : `${message.sender_name} recalled a message`
  }
  return locale === 'zh' ? '对方撤回了一条消息' : 'The other party recalled a message'
}

function RecallNotice({
  text,
  time,
  alignEnd,
  editLabel,
  onEdit,
}: {
  text: string
  time?: string
  alignEnd?: boolean
  editLabel?: string
  onEdit?: () => void
}) {
  return (
    <div className={cn('flex min-w-0 max-w-[75%] flex-col', alignEnd ? 'items-end' : 'items-start')}>
      <div className="max-w-full rounded-[18px] border border-dashed border-[#D8D8D8] bg-[#F5F5F5] px-3.5 py-2 text-sm leading-normal text-[#737373]">
        <span>{text}</span>
        {onEdit && editLabel && (
          <button
            type="button"
            className="ml-2 text-primary underline-offset-2 hover:underline"
            onClick={onEdit}
          >
            {editLabel}
          </button>
        )}
      </div>
      {time && (
        <span className="mt-1 text-[11px] text-[#999999]">{time}</span>
      )}
    </div>
  )
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
  if (status === 'unread') return locale === 'zh' ? '未读' : 'Unread'
  if (status === 'read') return locale === 'zh' ? '已读' : 'Read'
  return null
}

function OpenAgentAIDisclaimerNotice({
  content,
  locale,
}: {
  content: string
  locale: string
}) {
  const label = locale === 'zh' ? 'AI 免责声明' : 'AI disclaimer'

  return (
    <div className="mt-2 flex max-w-full items-start gap-1.5 text-[12px] leading-4 text-muted-foreground">
      <IconInfoCircle
        size={14}
        className="mt-px shrink-0"
        role="img"
        aria-label={label}
      />
      <span className="min-w-0 flex-1 break-words">{content}</span>
    </div>
  )
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
  const [manualExpanded, setManualExpanded] = useState<boolean | null>(() => (active ? true : null))
  const expanded = manualExpanded ?? active
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
        onClick={() => setManualExpanded(expanded ? false : true)}
        aria-expanded={expanded}
      >
        <span className="flex min-w-0 items-center gap-2 font-normal">
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

function OpenAgentFakeThinkingBubble() {
  return (
    <div
      className="inline-flex min-h-10 items-center gap-1 rounded-lg bg-[#F6F6F6] px-4 py-3 text-[#71717A]"
      role="status"
      aria-live="polite"
      aria-label="正在思考中"
    >
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-current opacity-70 motion-safe:animate-bounce [animation-delay:0ms] [animation-duration:900ms]" />
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-current opacity-70 motion-safe:animate-bounce [animation-delay:150ms] [animation-duration:900ms]" />
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-current opacity-70 motion-safe:animate-bounce [animation-delay:300ms] [animation-duration:900ms]" />
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
      className="flex min-h-10 w-full items-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-3 py-2 text-sm font-normal text-[#27272A]"
      data-open-agent-tool-call
    >
      <IconTool size={16} className="shrink-0 text-[#71717A]" aria-hidden />
      <span className="min-w-0 flex-1 truncate font-normal">
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

function OpenAgentTraceSummary({
  thinkingCount,
  toolCount,
  locale,
}: {
  thinkingCount: number
  toolCount: number
  locale: string
}) {
  const parts: string[] = []
  if (thinkingCount > 0) {
    parts.push(locale === 'zh' ? '已思考' : 'Thought')
  }
  if (toolCount > 0) {
    parts.push(locale === 'zh' ? `调用了 ${toolCount} 个工具` : `Used ${toolCount} tool${toolCount > 1 ? 's' : ''}`)
  }
  return <span className="font-normal">{parts.join(' · ') || (locale === 'zh' ? '查看过程' : 'View steps')}</span>
}

function OpenAgentProcessBlocks({
  thinkingBlocks,
  toolBlocks,
  locale,
  isStreaming,
}: {
  thinkingBlocks: ReturnType<typeof getOpenAgentThinkingBlocks>
  toolBlocks: OpenAgentToolBlock[]
  locale: string
  isStreaming: boolean
}) {
  const [manualOpen, setManualOpen] = useState<boolean | null>(null)
  const entries = [
    ...thinkingBlocks.map((block) => ({ type: 'thinking' as const, block, timelineIndex: block.timelineIndex })),
    ...toolBlocks.map((block) => ({ type: 'tool' as const, block, timelineIndex: block.timelineIndex })),
  ].sort((a, b) => a.timelineIndex - b.timelineIndex)

  if (entries.length === 0) return null

  const open = manualOpen ?? isStreaming

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setManualOpen(true)}
        className="flex min-h-9 w-full items-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-3 py-2 text-sm font-normal text-[#71717A] transition-colors hover:text-[#27272A]"
        aria-expanded={false}
      >
        <IconChevronRight size={16} className="shrink-0" aria-hidden />
        <OpenAgentTraceSummary
          thinkingCount={thinkingBlocks.length}
          toolCount={toolBlocks.length}
          locale={locale}
        />
      </button>
    )
  }

  return (
    <div className="space-y-2">
      {!isStreaming && (
        <button
          type="button"
          onClick={() => setManualOpen(false)}
          className="flex min-h-7 items-center gap-1.5 text-xs font-normal text-[#A1A1AA] transition-colors hover:text-[#71717A]"
          aria-expanded={true}
        >
          <IconChevronRight size={14} className="shrink-0 rotate-90" aria-hidden />
          <OpenAgentTraceSummary
            thinkingCount={thinkingBlocks.length}
            toolCount={toolBlocks.length}
            locale={locale}
          />
        </button>
      )}
      {entries.map((item) => (
        item.type === 'thinking' ? (
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

function StaticOpenAgentTraceBlocks({
  textBlocks,
  thinkingBlocks,
  toolBlocks,
  locale,
  bubbleStyle,
  isStreaming,
}: {
  textBlocks: OpenAgentTextBlock[]
  thinkingBlocks: ReturnType<typeof getOpenAgentThinkingBlocks>
  toolBlocks: OpenAgentToolBlock[]
  locale: string
  bubbleStyle: CSSProperties
  isStreaming: boolean
}) {
  const sortedTextBlocks = [...textBlocks].sort((a, b) => a.timelineIndex - b.timelineIndex)

  if (sortedTextBlocks.length === 0 && thinkingBlocks.length === 0 && toolBlocks.length === 0) return null

  return (
    <div className="space-y-2">
      <OpenAgentProcessBlocks
        thinkingBlocks={thinkingBlocks}
        toolBlocks={toolBlocks}
        locale={locale}
        isStreaming={isStreaming}
      />
      {sortedTextBlocks.map((block) => (
        <StaticOpenAgentTextBlock
          key={block.id}
          content={block.content}
          bubbleStyle={bubbleStyle}
        />
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
  allMessages = [],
  onEditRecalledMessage,
}: MessageBubbleProps) {
  const isUser = message.sender_type === 'visitor'
  const isAssistant = message.sender_type === 'agent' || message.sender_type === 'bot'
  const isBot = message.sender_type === 'bot'
  const assistantAvatarSrc = getAssistantAvatarSrc(message, config)
  const visitorChat = useVisitorChatConfig()
  const [messageMenu, setMessageMenu] = useState<{ x: number; y: number } | null>(null)
  const [longPressTimer, setLongPressTimer] = useState<ReturnType<typeof setTimeout> | null>(null)
  const textBlocks = isBot ? getOpenAgentTextBlocks(message.metadata) : []
  const thinkingBlocks = isBot ? getOpenAgentThinkingBlocks(message.metadata) : []
  const toolBlocks = isBot ? getOpenAgentToolBlocks(message.metadata) : []
  const visibleToolBlocks = toolBlocks.filter((block) => !isHumanHandoffToolBlock(block))
  const hasMessageText = message.content.trim().length > 0
  const hasVisibleOpenAgentText =
    hasMessageText || textBlocks.some((block) => block.content.trim().length > 0)
  const hasVisibleOpenAgentBlocks =
    textBlocks.length > 0 || thinkingBlocks.length > 0 || visibleToolBlocks.length > 0
  const openAgentTraceStreaming =
    message.metadata?.streaming === true
    || thinkingBlocks.some((block) => block.isStreaming)
    || visibleToolBlocks.some((block) => block.isExecuting)
    || textBlocks.some((block) => block.isStreaming)
  const isThinking =
    isBot
    && message.metadata?.streaming === true
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
  const isRichText = message.content_type === 'rich_text'
  const aiDisclaimerContent =
    config.open_agent_enabled && visitorChat.channel.open_agent_ai_disclaimer?.enabled
      ? visitorChat.channel.open_agent_ai_disclaimer.content.trim()
      : ''
  const isBotReplyContentType = message.content_type === 'text' || message.content_type === 'rich_text'
  const showAIDisclaimer =
    Boolean(aiDisclaimerContent)
    && isBot
    && isBotReplyContentType
    && !isThinking
    && !openAgentTraceStreaming
    && hasVisibleOpenAgentText
    && message.metadata?.event_type !== 'open_agent_handoff_event'
  const aiDisclaimerNotice = showAIDisclaimer ? (
    <OpenAgentAIDisclaimerNotice content={aiDisclaimerContent} locale={locale} />
  ) : null
  const offlineMessagePublicId =
    typeof message.metadata?.offline_message_public_id === 'string'
      ? message.metadata.offline_message_public_id
      : undefined
  const webSdkReadStatusEnabled = visitorChat.channel.read_status?.web_sdk_enabled ?? true
  const canShowReadStatus = isUser && webSdkReadStatusEnabled && !offlineMessagePublicId
  const effectiveStatus = messageStatus || message.status
  const statusText = canShowReadStatus ? statusLabel(effectiveStatus, locale) : null
  const quote = messageQuoteFromMetadata(message.metadata)
  const quotedOriginal = quote
    ? allMessages.find((item) => item.id === quote.message_id) ?? null
    : null
  const reeditQuotedMessage =
    quotedOriginal && canQuoteMessage(quotedOriginal, {
      canSend: !visitorChat.ended && !visitorChat.offlineMode,
      webChannel: true,
      closed: visitorChat.ended,
    })
      ? quotedOriginal
      : null
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
  const canRecall =
    isUser
    && !message.is_recalled
    && !visitorChat.ended
    && !visitorChat.offlineMode
    && message.id > 0
    && isRecallableContentType(message.content_type)
    && isWithinRecallWindow(message.created_at)
  const recallEditContent = typeof message.metadata?.recall_edit_content === 'string'
    ? message.metadata.recall_edit_content
    : ''
  const canEditRecalled =
    Boolean(onEditRecalledMessage)
    && isUser
    && message.is_recalled
    && !visitorChat.ended
    && !visitorChat.offlineMode
    && message.content_type === 'text'
    && recallEditContent.trim().length > 0
  const canQuoteCurrentMessage = canQuoteMessage(message, {
    canSend: !visitorChat.ended && !visitorChat.offlineMode,
    webChannel: true,
    closed: visitorChat.ended,
  })
  const hasMessageActions = canQuoteCurrentMessage || canRecall

  useEffect(() => {
    if (!messageMenu) return
    const close = () => setMessageMenu(null)
    window.addEventListener('click', close)
    window.addEventListener('scroll', close, true)
    window.addEventListener('keydown', close)
    return () => {
      window.removeEventListener('click', close)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('keydown', close)
    }
  }, [messageMenu])

  useEffect(() => {
    if (!longPressTimer) return
    return () => clearTimeout(longPressTimer)
  }, [longPressTimer])

  const openMessageMenu = useCallback((x: number, y: number) => {
    if (!hasMessageActions) return
    setMessageMenu({ x, y })
  }, [hasMessageActions])

  const handleRecall = useCallback(async () => {
    setMessageMenu(null)
    await visitorChat.onRecallMessage(message)
  }, [message, visitorChat])

  const handleQuote = useCallback(() => {
    setMessageMenu(null)
    visitorChat.onQuoteMessage(message)
  }, [message, visitorChat])

  const handleEditRecalled = useCallback(() => {
    if (!canEditRecalled || !onEditRecalledMessage) return
    onEditRecalledMessage({
      text: recallEditContent,
      contentType: 'text',
      quotedMessage: reeditQuotedMessage,
    })
  }, [canEditRecalled, onEditRecalledMessage, recallEditContent, reeditQuotedMessage])

  const handleContextMenu = useCallback((event: ReactMouseEvent<HTMLDivElement>) => {
    if (!hasMessageActions) return
    event.preventDefault()
    openMessageMenu(event.clientX, event.clientY)
  }, [hasMessageActions, openMessageMenu])

  const handleTouchStart = useCallback((event: ReactTouchEvent<HTMLDivElement>) => {
    if (!hasMessageActions) return
    const touch = event.touches[0]
    if (!touch) return
    const x = touch.clientX
    const y = touch.clientY
    const timer = setTimeout(() => {
      openMessageMenu(x, y)
    }, 550)
    setLongPressTimer(timer)
  }, [hasMessageActions, openMessageMenu])

  const clearLongPress = useCallback(() => {
    if (longPressTimer) clearTimeout(longPressTimer)
    setLongPressTimer(null)
  }, [longPressTimer])

  const messageMenuNode = messageMenu ? (
    <div
      className="fixed z-50 min-w-28 rounded-md border border-border bg-background p-1 text-sm shadow-lg"
      style={{ left: messageMenu.x, top: messageMenu.y }}
      onClick={(event) => event.stopPropagation()}
    >
      {canQuoteCurrentMessage && (
        <button
          type="button"
          className="flex w-full items-center rounded px-3 py-1.5 text-left text-foreground hover:bg-muted"
          onClick={handleQuote}
        >
          {t('ws.chat.quote.action', locale as Locale)}
        </button>
      )}
      {canRecall && (
        <button
          type="button"
          className="flex w-full items-center rounded px-3 py-1.5 text-left text-foreground hover:bg-muted"
          onClick={handleRecall}
        >
          {locale === 'zh' ? '撤回' : 'Recall'}
        </button>
      )}
    </div>
  ) : null
  const quoteAttachmentContext = {
    conversationId: message.conversation_id,
    conversationPublicId: message.conversation_public_id,
    visitorSessionToken: visitorChat.visitorSessionToken,
  }
  const quoteBlock = quote ? (
    <MessageQuoteBlock
      quote={quote}
      locale={locale as Locale}
      original={quotedOriginal}
      onClick={() => scrollToVisitorMessage(quote.message_id, locale)}
      audience="visitor"
      attachmentContext={quoteAttachmentContext}
      className="max-w-full rounded-lg"
    />
  ) : null
  const embeddedQuoteBlock = quote ? (
    <MessageQuoteBlock
      quote={quote}
      locale={locale as Locale}
      original={quotedOriginal}
      onClick={() => scrollToVisitorMessage(quote.message_id, locale)}
      variant="embedded"
      audience="visitor"
      attachmentContext={quoteAttachmentContext}
      className="mb-2"
    />
  ) : null

  if (message.is_recalled) {
    if (!shouldShowVisitorRecalledNotice(message)) return null

    return (
      <div className={cn('flex gap-2 px-5', isUser ? 'flex-row-reverse items-end' : 'flex-row items-start')}>
        {showAvatar && !isUser && assistantAvatarSrc && (
          <img
            src={assistantAvatarSrc}
            alt={message.sender_name || ''}
            className="h-9 w-9 shrink-0 rounded-full object-cover"
          />
        )}
        <RecallNotice
          text={recallText(message, locale)}
          time={showTime ? formatTime(message.created_at, locale) : undefined}
          alignEnd={isUser}
          editLabel={canEditRecalled ? t('ws.chat.recall.editAgain', locale as Locale) : undefined}
          onEdit={canEditRecalled ? handleEditRecalled : undefined}
        />
      </div>
    )
  }

  if (isEmptyBotBubble || isEmptyAssistantBubble) return null

  if (isBot && !attachmentContentType && renderAssistantParts && !hasVisibleOpenAgentBlocks && !isThinking) {
    return (
      <div
        className="flex flex-row items-start gap-2 px-5"
        onContextMenu={handleContextMenu}
        onTouchStart={handleTouchStart}
        onTouchMove={clearLongPress}
        onTouchEnd={clearLongPress}
        onTouchCancel={clearLongPress}
      >
        {messageMenuNode}
        {showAvatar && assistantAvatarSrc && (
          <img
            src={assistantAvatarSrc}
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
            {quoteBlock}
            <MessagePrimitive.Parts components={assistantPartsComponents} />
          </div>

          {aiDisclaimerNotice}
          {showTime && (
            <div className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
              <span>{formatTime(message.created_at, locale)}</span>
            </div>
          )}
          <OpenAgentFeedback
            messageId={message.id}
            senderType={message.sender_type}
            metadata={message.metadata}
            locale={locale}
            enabled={config.open_agent_enabled && config.open_agent_feedback_enabled}
            onSubmit={visitorChat.onSubmitOpenAgentFeedback}
          />
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
      <div
        className="flex flex-row items-start gap-2 px-5"
        onContextMenu={handleContextMenu}
        onTouchStart={handleTouchStart}
        onTouchMove={clearLongPress}
        onTouchEnd={clearLongPress}
        onTouchCancel={clearLongPress}
      >
        {messageMenuNode}
        {showAvatar && assistantAvatarSrc && (
          <img
            src={assistantAvatarSrc}
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
            {quoteBlock}
            {isThinking && thinkingBlocks.length === 0 && visibleToolBlocks.length === 0 && (
              <OpenAgentFakeThinkingBubble />
            )}
            <StaticOpenAgentTraceBlocks
              textBlocks={textBlocks}
              thinkingBlocks={thinkingBlocks}
              toolBlocks={visibleToolBlocks}
              locale={locale}
              bubbleStyle={bubbleStyle}
              isStreaming={openAgentTraceStreaming}
            />
            {textBlocks.length === 0 && (
              <StaticOpenAgentTextBlock content={message.content} bubbleStyle={bubbleStyle} />
            )}
          </div>

          {aiDisclaimerNotice}
          {showTime && (
            <div className="mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground">
              <span>{formatTime(message.created_at, locale)}</span>
            </div>
          )}
          <OpenAgentFeedback
            messageId={message.id}
            senderType={message.sender_type}
            metadata={message.metadata}
            locale={locale}
            enabled={config.open_agent_enabled && config.open_agent_feedback_enabled}
            onSubmit={visitorChat.onSubmitOpenAgentFeedback}
          />
        </div>
      </div>
    )
  }

  return (
    <div
      className={cn('flex gap-2 px-5', isUser ? 'flex-row-reverse items-end' : 'flex-row items-start')}
      onContextMenu={handleContextMenu}
      onTouchStart={handleTouchStart}
      onTouchMove={clearLongPress}
      onTouchEnd={clearLongPress}
      onTouchCancel={clearLongPress}
    >
      {messageMenuNode}
      {/* Avatar */}
      {showAvatar && !isUser && assistantAvatarSrc && (
        <img
          src={assistantAvatarSrc}
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
          <>
            {quoteBlock}
            <MessageAttachment
              conversationId={message.conversation_id}
              conversationPublicId={message.conversation_public_id}
              offlineMessagePublicId={offlineMessagePublicId}
              visitorSessionToken={visitorChat.visitorSessionToken}
              contentType={attachmentContentType}
              content={message.content}
            />
          </>
        ) : isRichText ? (
          quote ? (
            <div
              className={cn('max-w-full px-3 py-2 text-sm break-words break-all', !isUser && 'min-h-[42px]')}
              style={bubbleStyle}
            >
              {embeddedQuoteBlock}
              <RichTextMessageContent
                html={message.content}
                conversationId={message.conversation_id}
                conversationPublicId={message.conversation_public_id}
                visitorSessionToken={visitorChat.visitorSessionToken}
                className="max-w-full text-sm break-words break-all"
              />
            </div>
          ) : (
            <RichTextMessageContent
              html={message.content}
              conversationId={message.conversation_id}
              conversationPublicId={message.conversation_public_id}
              visitorSessionToken={visitorChat.visitorSessionToken}
              className={cn('max-w-full px-3 py-2 text-sm break-words break-all', !isUser && 'min-h-[42px]')}
              style={bubbleStyle}
            />
          )
        ) : (
          <div
            className={cn(
              'min-h-[42px] max-w-full px-3 py-2 text-sm',
              !isBot && !quote && 'flex items-center',
              isBot && 'break-words break-all whitespace-pre-wrap',
              isBot && [markdownTextRootClass, richTextListStyleClass],
            )}
            style={bubbleStyle}
          >
            {embeddedQuoteBlock}
            {isBot ? (
              <MarkdownText>{message.content}</MarkdownText>
            ) : (
              <span className="min-w-0 break-words break-all whitespace-pre-wrap leading-5">
                {message.content}
              </span>
            )}
          </div>
        )}

        {aiDisclaimerNotice}
        {(showTime || statusText) && (
          <div className={`mt-0.5 flex items-center gap-1 text-[10px] text-muted-foreground ${isUser ? 'flex-row-reverse' : ''}`}>
            {showTime && <span>{formatTime(message.created_at, locale)}</span>}
            {statusText && <span>{statusText}</span>}
          </div>
        )}
        {isBot && (
          <OpenAgentFeedback
            messageId={message.id}
            senderType={message.sender_type}
            metadata={message.metadata}
            locale={locale}
            enabled={config.open_agent_enabled && config.open_agent_feedback_enabled}
            onSubmit={visitorChat.onSubmitOpenAgentFeedback}
          />
        )}
      </div>
    </div>
  )
}
