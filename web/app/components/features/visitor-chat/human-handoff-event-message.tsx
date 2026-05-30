'use client'

import type { CSSProperties } from 'react'
import type { ChannelConfig } from '@/models/channel'

export type HandoffEventType =
  | 'confirm_requested'
  | 'confirmed_by_visitor'
  | 'auto_triggered'

export type HandoffConfirmCardState = 'active' | 'confirming' | 'dismissed' | null

type HumanHandoffConfirmCardProps = {
  locale: string
  handoffLabel: string
  state: 'active' | 'confirming' | 'dismissed'
  onConfirm: () => void
  onDismiss: () => void
}

type HumanHandoffEventMessageProps = {
  content: string
  config: ChannelConfig
  locale: string
  handoffEventType?: HandoffEventType | null
  confirmCardState?: HandoffConfirmCardState
  onConfirmHandoff?: () => void
  onDismissHandoff?: () => void
}

export function resolveHandoffEventType(metadata?: Record<string, unknown>): HandoffEventType | null {
  const value = metadata?.handoff_event_type
  if (
    value === 'confirm_requested'
    || value === 'confirmed_by_visitor'
    || value === 'auto_triggered'
  ) {
    return value
  }
  return null
}

export function isOpenAgentHandoffEventMessage(message: {
  metadata?: Record<string, unknown>
}) {
  return message.metadata?.event_type === 'open_agent_handoff_event'
}

export function isOpenAgentHandoffToolTrace(message: {
  sender_type?: string
  metadata?: Record<string, unknown>
}) {
  if (message.sender_type !== 'bot') return false
  const blocks = message.metadata?.open_agent_tool_blocks
  if (!Array.isArray(blocks)) return false
  return blocks.some((block) => {
    if (!block || typeof block !== 'object' || Array.isArray(block)) return false
    const record = block as Record<string, unknown>
    const toolName = record.toolName || record.tool_name
    return typeof toolName === 'string' && toolName.trim().toLowerCase() === 'human_handoff'
  })
}

export function resolveHandoffConfirmCardState(
  message: { id: number; metadata?: Record<string, unknown> },
  pending: { messageId?: number; toolCallId?: string } | null,
  dismissedToolCallIds: string[],
  confirmingToolCallIds: string[],
  confirmedToolCallIds: string[],
): HandoffConfirmCardState {
  const eventType = resolveHandoffEventType(message.metadata)
  const isConfirmRequest =
    eventType === 'confirm_requested'
    || (eventType === null && message.metadata?.event_type === 'open_agent_handoff_event')
  if (!isConfirmRequest) return null

  const toolCallId = typeof message.metadata?.tool_call_id === 'string'
    ? message.metadata.tool_call_id
    : undefined

  if (toolCallId && confirmedToolCallIds.includes(toolCallId)) {
    return null
  }

  if (toolCallId && dismissedToolCallIds.includes(toolCallId)) {
    return 'dismissed'
  }

  if (dismissedToolCallIds.includes(`message_${message.id}`)) {
    return 'dismissed'
  }

  if (toolCallId && confirmingToolCallIds.includes(toolCallId)) {
    return 'confirming'
  }

  if (!pending) return null

  if (pending.messageId != null && pending.messageId === message.id) {
    return 'active'
  }

  if (toolCallId && pending.toolCallId && pending.toolCallId === toolCallId) {
    return 'active'
  }

  return null
}

export function collectConfirmedHandoffToolCallIds(
  messages: Array<{ metadata?: Record<string, unknown> }>,
): string[] {
  const ids: string[] = []
  for (const message of messages) {
    const metadata = message.metadata
    if (
      metadata?.event_type === 'open_agent_handoff_event'
      && metadata.handoff_event_type === 'confirmed_by_visitor'
      && typeof metadata.tool_call_id === 'string'
    ) {
      ids.push(metadata.tool_call_id)
    }
  }
  return ids
}

function resolveEventLabel(
  handoffEventType: HandoffEventType | null,
  locale: string,
): string {
  if (handoffEventType === 'auto_triggered') {
    return locale === 'zh' ? '机器人自动触发转人工' : 'Bot auto-triggered human handoff'
  }
  if (handoffEventType === 'confirmed_by_visitor') {
    return locale === 'zh' ? '用户已确认转人工' : 'Visitor confirmed human handoff'
  }
  return locale === 'zh' ? '请求用户确认转人工' : 'Human handoff confirmation requested'
}

function HumanHandoffConfirmCard({
  locale,
  handoffLabel,
  state,
  onConfirm,
  onDismiss,
}: HumanHandoffConfirmCardProps) {
  const isDismissed = state === 'dismissed'
  const isConfirming = state === 'confirming'
  const isDisabled = isDismissed || isConfirming

  return (
    <div className="mx-5 mt-2 rounded-xl border border-border bg-card p-3 text-sm shadow-sm">
      <p className="mb-3 font-medium leading-5 text-foreground">
        {locale === 'zh' ? '是否需要为您转接人工客服？' : 'Would you like to transfer to human support?'}
      </p>
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          disabled={isDisabled}
          className="h-10 rounded-md bg-[#1A1A1A] px-3 text-sm font-medium text-[var(--opendesk-send-button-bg)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          onClick={onConfirm}
        >
          {isConfirming
            ? (locale === 'zh' ? '转接中...' : 'Connecting...')
            : handoffLabel}
        </button>
        <button
          type="button"
          disabled={isDisabled}
          className={
            isDismissed
              ? 'h-10 rounded-md border border-border bg-muted px-3 text-sm font-medium text-foreground'
              : 'h-10 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50'
          }
          onClick={onDismiss}
        >
          {locale === 'zh' ? '继续咨询智能助手' : 'Keep chatting'}
        </button>
      </div>
    </div>
  )
}

export function HumanHandoffEventMessage({
  config,
  locale,
  handoffEventType = null,
  confirmCardState = null,
  onConfirmHandoff,
  onDismissHandoff,
}: HumanHandoffEventMessageProps) {
  const eventLabel = resolveEventLabel(handoffEventType, locale)
  const handoffLabel = config.open_agent_handoff_label || (locale === 'zh' ? '转人工' : 'Human support')
  const handoffButtonStyle = {
    '--opendesk-send-button-bg': config.send_button_bg_color || 'var(--color-primary)',
  } as CSSProperties

  return (
    <div className="space-y-2" style={handoffButtonStyle}>
      <div className="flex justify-center py-1">
        <span className="rounded-md bg-secondary px-3 py-1 text-xs text-muted-foreground">
          {eventLabel}
        </span>
      </div>

      {confirmCardState && (
        <HumanHandoffConfirmCard
          locale={locale}
          handoffLabel={handoffLabel}
          state={confirmCardState}
          onConfirm={onConfirmHandoff ?? (() => {})}
          onDismiss={onDismissHandoff ?? (() => {})}
        />
      )}
    </div>
  )
}
