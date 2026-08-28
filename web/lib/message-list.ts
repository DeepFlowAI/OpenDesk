import type { Message } from '@/models/conversation'

export function dedupeMessagesById(messages: Message[]): Message[] {
  const seen = new Set<number>()
  for (const message of messages) {
    if (seen.has(message.id)) {
      return collapseMessagesById(messages)
    }
    seen.add(message.id)
  }
  return messages
}

function collapseMessagesById(messages: Message[]): Message[] {
  const indexes = new Map<number, number>()
  const next: Message[] = []
  for (const message of messages) {
    const index = indexes.get(message.id)
    if (index === undefined) {
      indexes.set(message.id, next.length)
      next.push(message)
    } else {
      next[index] = message
    }
  }
  return next
}
