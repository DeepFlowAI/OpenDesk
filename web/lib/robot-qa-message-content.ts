import TurndownService from 'turndown'

import { htmlToPlainText } from '@/lib/clipboard'
import type { Message } from '@/models/conversation'

const ROBOT_QA_SENDER_TYPES = new Set(['visitor', 'agent', 'bot'])

export function canCreateRobotQaFromMessage(message: Message): boolean {
  if (message.is_recalled || message.metadata?.is_recalled) return false
  if (!ROBOT_QA_SENDER_TYPES.has(message.sender_type)) return false
  if (message.content_type !== 'text' && message.content_type !== 'rich_text') return false

  const visibleContent = message.content_type === 'rich_text'
    ? htmlToPlainText(message.content)
    : message.content.trim()
  return visibleContent.length > 0
}

export function robotQaAnswerMarkdownFromMessage(message: Message): string {
  if (message.content_type !== 'rich_text') return message.content.trim()

  return new TurndownService({
    bulletListMarker: '-',
    headingStyle: 'atx',
  }).turndown(message.content).trim()
}

export function normalizeRobotQaKeyword(value: string): string | null {
  const normalized = value.trim().toLowerCase()
  return normalized && /^[a-z0-9_]+$/.test(normalized) ? normalized : null
}
