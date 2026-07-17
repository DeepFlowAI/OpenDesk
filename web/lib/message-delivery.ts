import type { Message } from '@/models/conversation'

const DELIVERABLE_CONTENT_TYPES = new Set<Message['content_type']>([
  'text',
  'rich_text',
  'image',
  'file',
])

export type MessageDeliverySource = {
  conversationPublicId?: string | null
  messages: Message[]
}

export type MessageDeliveryBatch = {
  conversationPublicId: string
  messageIds: number[]
}

export function buildMessageDeliveryBatches(sources: MessageDeliverySource[]): MessageDeliveryBatch[] {
  const idsByConversation = new Map<string, Set<number>>()

  for (const source of sources) {
    for (const message of source.messages) {
      if (
        message.id <= 0
        || message.sender_type !== 'agent'
        || !DELIVERABLE_CONTENT_TYPES.has(message.content_type)
      ) {
        continue
      }
      const conversationPublicId = message.conversation_public_id || source.conversationPublicId
      if (!conversationPublicId) continue
      const ids = idsByConversation.get(conversationPublicId) ?? new Set<number>()
      ids.add(message.id)
      idsByConversation.set(conversationPublicId, ids)
    }
  }

  return Array.from(idsByConversation, ([conversationPublicId, ids]) => ({
    conversationPublicId,
    messageIds: Array.from(ids).sort((left, right) => left - right),
  }))
}
