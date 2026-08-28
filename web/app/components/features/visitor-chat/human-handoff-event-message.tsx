'use client'

import type { CSSProperties } from 'react'
import type { ChannelConfig } from '@/models/channel'
import type { Locale } from '@/context/locale-store'
import { SafeHtml } from '@/components/safe-html'
import { t } from '@/utils/i18n'

export type HandoffEventType =
  | 'confirm_requested'
  | 'confirmed_by_visitor'
  | 'auto_triggered'

export type HandoffConfirmCardState = 'active' | 'confirming' | 'dismissed' | null

type HumanHandoffConfirmCardProps = {
  locale: Locale
  handoffLabel: string
  state: 'active' | 'confirming' | 'dismissed'
  onConfirm: () => void
  onDismiss: () => void
}

type HumanHandoffEventMessageProps = {
  content: string
  config: ChannelConfig
  locale: Locale
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
  locale: Locale,
): string {
  if (handoffEventType === 'auto_triggered') {
    return t('chat.handoff.autoTriggered', locale)
  }
  if (handoffEventType === 'confirmed_by_visitor') {
    return t('chat.handoff.confirmed', locale)
  }
  return t('chat.handoff.requested', locale)
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
        {t('chat.handoff.confirmPrompt', locale)}
      </p>
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          data-action="request-handoff"
          disabled={isDisabled}
          className="h-10 rounded-md bg-[var(--opendesk-send-button-bg)] px-3 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          onClick={onConfirm}
        >
          {isConfirming
            ? t('chat.handoff.connectingDots', locale)
            : handoffLabel}
        </button>
        <button
          type="button"
          data-action="dismiss-handoff"
          disabled={isDisabled}
          className={
            isDismissed
              ? 'h-10 rounded-md border border-border bg-muted px-3 text-sm font-medium text-foreground'
              : 'h-10 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground transition-colors hover:bg-muted disabled:cursor-not-allowed disabled:opacity-50'
          }
          onClick={onDismiss}
        >
          {t('chat.handoff.keepChatting', locale)}
        </button>
      </div>
    </div>
  )
}

type HandoffQueueFullCardProps = {
  locale: Locale
  message: string
  showLeaveMessageButton: boolean
  leaveMessageButtonLabel: string
  sendButtonBgColor?: string | null
  onLeaveMessage: () => void
  onContinueBot: () => void
}

export function HandoffQueueFullCard({
  locale,
  message,
  showLeaveMessageButton,
  leaveMessageButtonLabel,
  sendButtonBgColor,
  onLeaveMessage,
  onContinueBot,
}: HandoffQueueFullCardProps) {
  const cardStyle = {
    '--opendesk-send-button-bg': sendButtonBgColor || 'var(--color-primary)',
  } as CSSProperties
  const continueLabel = t('chat.handoff.keepChatting', locale)
  const leaveLabel = leaveMessageButtonLabel || t('chat.leaveMessage.button', locale)

  return (
    <div
      className="mx-5 mt-2 rounded-xl border border-border bg-card p-3 text-sm shadow-sm"
      style={cardStyle}
    >
      {message && (
        <SafeHtml
          className="prose prose-sm mb-3 max-w-none leading-5 text-foreground"
          html={message}
        />
      )}
      <div className={showLeaveMessageButton ? 'grid grid-cols-2 gap-2' : 'grid grid-cols-1 gap-2'}>
        {showLeaveMessageButton && (
          <button
            type="button"
            data-action="queue-full-leave-message"
            className="h-10 rounded-md bg-[var(--opendesk-send-button-bg)] px-3 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
            onClick={onLeaveMessage}
          >
            {leaveLabel}
          </button>
        )}
        <button
          type="button"
          data-action="continue-bot"
          className="h-10 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground transition-colors hover:bg-muted"
          onClick={onContinueBot}
        >
          {continueLabel}
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
  const handoffLabel = config.open_agent_handoff_label || t('chat.handoff.button', locale)
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
