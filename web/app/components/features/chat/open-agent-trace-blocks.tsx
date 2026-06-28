'use client'

import { useState } from 'react'
import { IconChevronRight, IconLoader2, IconTool } from '@tabler/icons-react'
import { cn } from '@/lib/utils'
import { richTextListStyleClass } from '@/lib/rich-text-body-classes'
import { MarkdownText, markdownTextRootClass } from '@/components/assistant-ui/markdown-text'
import type {
  OpenAgentTextBlock,
  OpenAgentThinkingBlock as OpenAgentThinkingBlockType,
  OpenAgentToolBlock,
} from '@/models/conversation'

const BOT_BUBBLE_CLASS = 'rounded-lg bg-secondary px-3 py-2 text-sm text-foreground break-words break-all whitespace-pre-wrap max-w-full min-w-0'

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
        <div className="whitespace-pre-wrap break-words break-all px-3 pb-3 pl-9 text-xs leading-5 text-[#52525B]">
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

export function OpenAgentTraceBlocks({
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
