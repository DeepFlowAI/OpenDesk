import { isWelcomeLikeContentType } from '@/lib/welcome-message-content-type'
import type { Message } from '@/models/conversation'

const CONTENT_SENDERS = new Set<Message['sender_type']>(['visitor', 'agent', 'bot'])
const CONTENT_TYPES = new Set<Message['content_type']>(['text', 'rich_text', 'image', 'file'])

export function isConversationHistoryContentMessage(message: Message): boolean {
  if (isWelcomeLikeContentType(message.content_type)) return true
  return CONTENT_SENDERS.has(message.sender_type) && CONTENT_TYPES.has(message.content_type)
}
