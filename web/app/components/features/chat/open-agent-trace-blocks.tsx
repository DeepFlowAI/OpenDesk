'use client'

import { useState } from 'react'
import { IconChevronRight, IconLoader2, IconTool } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { MarkdownText, markdownTextRootClass } from '@/components/assistant-ui/markdown-text'
import type { Locale } from '@/context/locale-store'
import { t } from '@/utils/i18n'
import type {
  OpenAgentTextBlock,
  OpenAgentThinkingBlock as OpenAgentThinkingBlockType,
  OpenAgentToolBlock,
} from '@/models/conversation'

const BOT_BUBBLE_CLASS = 'rounded-lg bg-secondary px-3 py-2 text-sm text-foreground break-words break-all whitespace-pre-wrap max-w-full min-w-0'
const FOLLOW_CONTENT_WIDTH_CLASS = 'w-0 min-w-full'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function getStringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function getNumberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function stripOpenAgentThinkSections(content: string): string {
  return content
    .replace(/<think>[\s\S]*?<\/think>/gi, '')
    .replace(/<think>[\s\S]*$/gi, '')
    .replace(/<\/think>/gi, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function isHumanHandoffToolBlock(block: OpenAgentToolBlock): boolean {
  return block.toolName.trim().toLowerCase() === 'human_handoff' || block.usedForHandoff === true
}

export function getOpenAgentThinkingBlocks(metadata?: Record<string, unknown>): OpenAgentThinkingBlockType[] {
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

export function getOpenAgentToolBlocks(metadata?: Record<string, unknown>): OpenAgentToolBlock[] {
  const value = metadata?.open_agent_tool_blocks
  if (!Array.isArray(value)) return []

  return value.flatMap((item): OpenAgentToolBlock[] => {
    if (!isRecord(item)) return []
    const toolCallId = (
      getStringValue(item.toolCallId)
      || getStringValue(item.tool_call_id)
      || getStringValue(item.call_id)
    )
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
      usedForHandoff: item.usedForHandoff === true || item.used_for_handoff === true,
    }]
  })
}

export function getOpenAgentTextBlocks(metadata?: Record<string, unknown>): OpenAgentTextBlock[] {
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

export function getVisibleOpenAgentToolBlocks(metadata?: Record<string, unknown>): OpenAgentToolBlock[] {
  return getOpenAgentToolBlocks(metadata).filter((block) => !isHumanHandoffToolBlock(block))
}

function OpenAgentThinkingBlock({
  locale,
  active = false,
  content = '',
}: {
  locale: Locale
  active?: boolean
  content?: string
}) {
  const [manualExpanded, setManualExpanded] = useState<boolean | null>(() => (active ? true : null))
  const expanded = manualExpanded ?? active
  const hasContent = content.trim().length > 0

  return (
    <div className="min-w-0 max-w-full rounded-lg bg-[#F6F6F6] text-sm text-[#71717A]" data-open-agent-thinking>
      <button
        type="button"
        className="flex min-h-9 w-full items-center justify-between gap-2 px-3 py-2 text-left"
        onClick={() => setManualExpanded(expanded ? false : true)}
        aria-expanded={expanded}
      >
        <span className="flex min-w-0 items-center gap-2 font-medium">
          <IconChevronRight
            size={16}
            className={cn('shrink-0 transition-transform', expanded && 'rotate-90')}
            aria-hidden
          />
          <span>{t('chat.ai.thinking', locale)}</span>
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
        <div className="min-w-0 max-w-full whitespace-pre-wrap break-words break-all px-3 pb-3 pl-9 text-xs leading-5 text-[#52525B]">
          {content}
        </div>
      )}
    </div>
  )
}

function OpenAgentToolBlockView({ block, locale }: { block: OpenAgentToolBlock; locale: Locale }) {
  return (
    <div
      className="flex min-h-10 w-full min-w-0 items-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-3 py-2 text-sm text-[#27272A] shadow-sm"
      data-open-agent-tool-call
    >
      <IconTool size={16} className="shrink-0 text-[#71717A]" aria-hidden />
      <span className="min-w-0 flex-1 truncate">
        {block.brief || block.toolName || t('chat.ai.toolCall', locale)}
      </span>
      {block.isExecuting && (
        <IconLoader2 size={16} className="shrink-0 animate-spin text-[#A1A1AA]" aria-hidden />
      )}
    </div>
  )
}

export function OpenAgentTextBlockView({
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

function OpenAgentTraceSummary({
  thinkingCount,
  toolCount,
  locale,
}: {
  thinkingCount: number
  toolCount: number
  locale: Locale
}) {
  const parts: string[] = []
  if (thinkingCount > 0) {
    parts.push(t('chat.ai.thought', locale))
  }
  if (toolCount > 0) {
    parts.push(t('chat.ai.usedTools', locale, { count: toolCount }))
  }
  return <span className="font-normal">{parts.join(' · ') || t('chat.ai.viewSteps', locale)}</span>
}

function OpenAgentProcessBlocks({
  thinkingBlocks,
  toolBlocks,
  locale,
  isStreaming,
  followContentWidth,
}: {
  thinkingBlocks: OpenAgentThinkingBlockType[]
  toolBlocks: OpenAgentToolBlock[]
  locale: Locale
  isStreaming: boolean
  followContentWidth: boolean
}) {
  const [manualOpen, setManualOpen] = useState<boolean | null>(null)
  const entries = [
    ...thinkingBlocks.map((block) => ({ type: 'thinking' as const, block, timelineIndex: block.timelineIndex })),
    ...toolBlocks.map((block) => ({ type: 'tool' as const, block, timelineIndex: block.timelineIndex })),
  ].sort((a, b) => a.timelineIndex - b.timelineIndex)

  if (entries.length === 0) return null

  const open = manualOpen ?? isStreaming
  const widthClass = followContentWidth ? FOLLOW_CONTENT_WIDTH_CLASS : 'w-full min-w-0'

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setManualOpen(true)}
        className={cn(
          'flex min-h-9 items-center gap-2 rounded-lg border border-[#E5E7EB] bg-white px-3 py-2 text-sm font-normal text-[#71717A] transition-colors hover:text-[#27272A]',
          widthClass,
        )}
        aria-expanded={false}
        data-open-agent-process
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
    <div className={cn('space-y-2', widthClass)} data-open-agent-process data-open-agent-process-open="">
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
          <OpenAgentToolBlockView key={item.block.id} block={item.block} locale={locale} />
        )
      ))}
    </div>
  )
}

export function OpenAgentTraceBlocks({
  textBlocks,
  thinkingBlocks,
  toolBlocks,
  locale,
  isStreaming = false,
  followContentWidth = false,
}: {
  textBlocks: OpenAgentTextBlock[]
  thinkingBlocks: OpenAgentThinkingBlockType[]
  toolBlocks: OpenAgentToolBlock[]
  locale: Locale
  isStreaming?: boolean
  followContentWidth?: boolean
}) {
  const sortedTextBlocks = [...textBlocks].sort((a, b) => a.timelineIndex - b.timelineIndex)
  const hasAnswerText = sortedTextBlocks.length > 0

  if (!hasAnswerText && thinkingBlocks.length === 0 && toolBlocks.length === 0) return null

  return (
    <div className={cn(
      'min-w-0 max-w-full space-y-2',
      followContentWidth && !hasAnswerText && FOLLOW_CONTENT_WIDTH_CLASS,
    )}>
      <OpenAgentProcessBlocks
        thinkingBlocks={thinkingBlocks}
        toolBlocks={toolBlocks}
        locale={locale}
        isStreaming={isStreaming}
        followContentWidth={hasAnswerText}
      />
      {sortedTextBlocks.map((block) => (
        <OpenAgentTextBlockView key={block.id} content={block.content} />
      ))}
    </div>
  )
}
